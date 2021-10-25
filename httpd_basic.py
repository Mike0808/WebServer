import logging
import mimetypes
import os
import re
import time
from datetime import datetime
import multiprocessing as mp
import threading as th
from optparse import OptionParser
from urllib.parse import unquote
import asyncore_epoll
from sys import platform
from email.parser import Parser


op = OptionParser()
op.add_option("-w", "--worker", action="store", type=str, help="Setup worker count",
                    default=10)
op.add_option("-g", "--logdir", action="store", type=str, help="From where will be processed logs",
                    default='.')
op.add_option("-l", "--log", action="store", type=str, help="Log filename.", default="app_webserver.log")
(opts, args) = op.parse_args()

logging.basicConfig(filename=opts.log,
                    filemode='w',
                    level=logging.DEBUG,
                    format="%(created)-15s %(msecs)d %(levelname)8s %(thread)d %(name)s %(message)s")
log = logging.getLogger(__name__)

BACKLOG = 5
SIZE = 1024

DEFAULT_ERROR_MESSAGE = """\
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
        "http://www.w3.org/TR/html4/strict.dtd">
<html>
    <head>
        <meta http-equiv="Content-Type" content="text/html;charset=utf-8">
        <title>Error response</title>
    </head>
    <body>
        <h1>Error response</h1>
        <p>Error code: {code}d</p>
        <p>Message: {message}s.</p>
        <p>Error code explanation: {code}s - {explain}s.</p>
    </body>
</html>\r
"""

HEADER = """\
HTTP/1.1 {code} {explain}\r
Date: {date}\r
Server: {servername}\r
Content-Length: {length}\r
Content-Type: {type}\r
Connection: {conn}\r
"""

MIME = {'css': 'text/css',
        'html': 'text/html',
        'js': 'application/javascript',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'swf': 'application/x-shockwave-flash'}

ACC_MIME = ['css', 'html', 'js', 'jpg', 'jpeg', 'png', 'gif', 'swf', 'txt']

DEFAULT_TIMEOUT = 0

DATE = datetime.now().strftime("%a %d %b %Y, %H:%M:%S GMT")


class EchoHandler(asyncore_epoll.dispatcher):

    def __init__(self, conn_sock, client_address, server):
        self.server = server
        self.client_address = client_address
        self.buffer = b""

        self.is_readable = True
        # We dont have anything to write, to start with
        self.is_writable = False

        # Create ourselves, but with an already provided socket
        asyncore_epoll.dispatcher.__init__(self, conn_sock)
        log.debug("created handler; waiting for loop")

    def readable(self):
        return self.is_readable

    def writable(self):
        return self.is_writable

    def handle_connect(self):
        log.info("#################")
        self.connect(self.client_address)

    def handle_read(self):
        log.debug("handle read")
        data = self.recv(SIZE)
        log.debug("after recv")
        if data:
            log.debug("got data")
            self.buffer += data
            if self.buffer.endswith(b'\r\n\r\n'):
                self.is_writable = True  # sth to send back now
                self.is_readable = False
        else:
            log.debug("got null data")

    def handle_write(self):
        log.debug("handle_write")
        message = self._processor(self.buffer)
        content_length = len(message)
        if message:
            while len(message) != 0:
                sent = self.send(message)
                message = message[sent:]
            log.debug("sent data")

        else:
            log.debug("nothing to send")
        if len(message) == 0:
            self.is_writable = False
            self.is_readable = True
            self.handle_close()

    def handle_close(self):
        log.debug("handle_close")
        log.info("conn_closed: client_address=%s:%s" % \
                 (self.client_address[0],
                  self.client_address[1]))
        self.close()
        # pass

    @staticmethod
    def _processor(buffer, date=DATE, document_root=''):
        # Accept the browser sent me the http request
        try:
            request_str = buffer.decode('utf-8')
            req, header_alone = http_req_line_parser(request_str)
            req_header = http_parse_header(header_alone)
            method, target, ver = http_parse_request_line(req)
            file_name = http_parse_file_name(unquote(target))
            path = check_for_long_path(os.path.join(file_name), document_root)
            ext = get_filename_ext(path)
            http_status_error_response(method, target, ver, path, ext)
            content_type = http_content_type(ext)
            header = http_header_gen(path, req_header, content_type)
            if method == 'head':
                return header + b'\r\n'
            body = http_body_gen(path, content_type)
            return header + b'\r\n' + body + b'\r\n'
        except Exception as e:
            if hasattr(e, 'status'):
                err = HTTPError(e.status, e.reason, e.body, date, 'Error')
                logging.error("ERROR Occured status - {}, reason - {}, date - {}, host - {}".format(e.status,
                                                                                                    e.reason,
                                                                                                    date,
                                                                                                    'Error'))
            else:
                err = HTTPError('405', 'Method Not Implemented', 'Request Error', date)
                logging.error(
                    "ERROR Occured status - 405, reason - Method Not Implemented, date - {}".format(date))
            return err.error_content()


def check_for_long_path(path, document_root):
    abs_path = os.path.abspath(path)
    base_path = os.path.abspath(document_root) if document_root else os.path.abspath('.')
    path_join = os.path.join(base_path, abs_path)
    if base_path in path_join:
        return path_join
    return document_root


def http_body_gen(path, content_type):
    """
    Returns body of opened file
    """
    if 'image' or 'application' in content_type:
        with open(path, "rb") as f:
            body = f.read()
    else:
        with open(path, "r") as f:
            body = f.read().encode("utf-8")
    return body


def http_header_gen(path, header, content_type, date=DATE):
    """
    Generate and return header
    """
    header = HEADER.format(code='200',
                           explain='OK',
                           date=date,
                           servername=header.get("Host"),
                           length=os.path.getsize(path),
                           type=content_type,
                           conn='Close').encode("utf-8")
    return header


def http_parse_file_name(request_line):
    """
    Splitting request line for looking up path, filename and content_type
    """
    if "?" in request_line:
        parsed_url, args = request_line.split("?")
        parsed_url = parsed_url.split("/")
    else:
        parsed_url = request_line.split('/')
    if parsed_url[-1] == "":
        file_name = '/'.join(parsed_url[1:])
        file_name += "index.html"
    else:
        file_name = '/'.join(parsed_url[1:])
    return file_name


def get_filename_ext(path):
    """
    select and get extension of file
    :param path:
    :return: extension of filename
    """
    *_, ext = path.split('.')
    return ext


def http_content_type(ext):
    # looking for accepted files for content-type format
    return mimetypes.types_map['.' + ext]


def http_req_line_parser(line):
    """
    Parsing uri line
    :param request line:
    :return:
    """
    try:
        req, header_only = line.split('\r\n', 1)
        return req, header_only
    except Exception:
        raise HTTPError(400, 'Bad request', 'Malformed request line')


def http_parse_header(headers_alone):
    """
    Parsing header messages
    """
    return Parser().parsestr(headers_alone)


def http_parse_request_line(req):
    """
    Analyze the first line of header
    """
    if len(req.split()) != 3:
        raise HTTPError(400, 'Bad request', 'Malformed request line')
    method, target, ver = req.split()
    return method.lower(), target, ver



def http_status_error_response(method, target, ver, path, ext):
    """
    Error validator
    """
    if float(ver.split('/')[1]) < 1:
        raise HTTPError(505, 'HTTP Version Not Supported')
    if method not in ['get', 'head']:
        raise HTTPError(405, 'Method Not Allowed')

    if not os.path.exists(path):
        raise HTTPError(404, 'Not Found')
    if ext not in ACC_MIME:
        raise HTTPError(404, 'Not Found', 'Content-type not support')


class HTTPError(Exception):
    """
    Error creator
    """

    def __init__(self, status, reason, body=None, date=None, servername=None):
        super().__init__()
        self.status = status
        self.reason = reason
        self.body = body
        self.date = date
        self.servername = servername

    def error_content(self):
        res_body = DEFAULT_ERROR_MESSAGE.format(code=self.status,
                                                message=self.body,
                                                explain=self.reason).encode("utf-8")
        resposne_header = HEADER.format(code=self.status,
                                        explain=self.reason,
                                        date=self.date,
                                        servername=self.servername,
                                        length=len(res_body),
                                        type='Not Implemented',
                                        conn='Close').encode("utf-8")
        response = resposne_header + b'\r\n' + res_body + b'\r\n'
        return response


class EchoServer(asyncore_epoll.dispatcher):
    _allow_reuse_port = True
    request_queue_size = 5

    def __init__(self, address, handlerClass=EchoHandler):
        self.address = address
        self.handlerClass = handlerClass

        asyncore_epoll.dispatcher.__init__(self)
        self.create_socket()

        if self._allow_reuse_port:
            self.set_reuse_port()

        self.server_bind()
        self.server_activate()

    def server_bind(self):
        self.bind(self.address)
        log.debug("bind: address=%s:%s" % (self.address[0], self.address[1]))

    def server_activate(self):
        self.listen(self.request_queue_size)
        log.debug("listen: backlog=%d" % self.request_queue_size)

    def fileno(self):
        return self.socket.fileno()

    def serve_forever(self):
        if "darwin" == platform:
            logging.info("Starting webserver...")
            poller = asyncore_epoll.kqueue_poller
        else:
            logging.info("Starting webserver...")
            poller = asyncore_epoll.epoll_poller
        asyncore_epoll.loop(poller=poller)

    def handle_request(self):
        pass

    # # Internal use
    def handle_accept(self):
        (conn_sock, client_address) = self.accept()
        if self.verify_request(conn_sock, client_address):
            self.process_request(conn_sock, client_address)

    def verify_request(self, conn_sock, client_address):
        return True

    def process_request(self, conn_sock, client_address):
        log.info("conn_made: client_address=%s:%s" % \
                 (client_address[0],
                  client_address[1]))
        self.handlerClass(conn_sock, client_address, self)

    def handle_close(self):
        log.info("connection closed")
        self.close()


def worker():
    interface = "0.0.0.0"
    port = 8080
    server = EchoServer((interface, port))
    server.serve_forever()


def main():
    workers = [mp.Process(target=worker, daemon=True) for i in range(int(opts.worker))]
    for p in workers:
        p.start()
    for p in workers:
        p.join()


if __name__ == '__main__':
    main()
