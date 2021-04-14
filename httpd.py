import logging
import mimetypes
import os
import re
import select
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.parser import Parser
from optparse import OptionParser
from socket import socket, error, \
    AF_INET, SOCK_STREAM, \
    SOL_SOCKET, SO_REUSEADDR
from sys import platform
from urllib.parse import unquote

# MAX_LINE = 64 * 1024
# MAX_HEADERS = 100
# Default error message template
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

# DEFAULT_ERROR_CONTENT_TYPE = "text/html;charset=utf-8"

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

DEFAULT_BUFFSIZE = 1024

DATE = datetime.now().strftime("%a %d %b %Y, %H:%M:%S GMT")


class MyHTTPServer:
    def __init__(self, host, port, server_name):
        self._host = host
        self._port = port
        self._server_name = server_name

    def http_server_init(self):
        # Create a socket
        http_server = socket(AF_INET, SOCK_STREAM)
        logging.info("Creating server TCP socket...")
        # Prevent port is occupied not start program
        http_server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        # Bind port
        http_server.bind((self._host, self._port))
        logging.info("Web server started at {host}:{port}".format(host=self._host, port=self._port))
        # Goes listening socket
        http_server.listen(128)
        # Set the socket is blocked manner
        http_server.setblocking(False)
        return http_server


class PollQueue:
    def __init__(self, httpd_server, processor, thr_count=2, timeout=DEFAULT_TIMEOUT):
        self._document_root = ''
        self._buffsize = DEFAULT_BUFFSIZE
        self._response_body = DEFAULT_ERROR_MESSAGE
        self._timeout = timeout
        self._processor = processor
        self._httpd_server = httpd_server
        self._thr_count = thr_count

    def epoll_serve_forever(self, response=None):
        # Create an epoll objects
        epl = select.epoll()
        # Corresponding to the listening socket fd (file descriptor) registered to the epoll
        epl.register(self._httpd_server.fileno(), select.EPOLLIN)
        logging.info("FD {fd} registred in epoll".format(fd=self._httpd_server.fileno()))
        try:
            # Correspondence between storage and file descriptor fd socket
            fd_event_dict = {}
            requests = {}
            responses = {}
            while True:
                # Default clog, known os detected data arrives, tell the program through
                # an event notification method, this time will de-clog
                fd_event_list = epl.poll()
                for fd, event in fd_event_list:
                    # If the data over the listening socket, that is waiting for new client connections
                    if fd == self._httpd_server.fileno():
                        client, info = self._httpd_server.accept()
                        client.setblocking(False)
                        # The new socket is registered in epoll
                        epl.register(client.fileno(), select.EPOLLIN)
                        # The correspondence between file descriptors and sockets into dictionary
                        fd_event_dict[client.fileno()] = client
                        requests[client.fileno()] = b''
                        responses[client.fileno()] = response
                    elif event == select.EPOLLIN:
                        # Judge whether a socket connected data sent me
                        with ThreadPoolExecutor(max_workers=self._thr_count) as executor:
                            worker = ThreadingEcho(fd_event_dict[fd], self._processor)
                            executor.submit(worker.handle_connection())
        finally:
            epl.unregister(self._httpd_server.fileno())
            epl.close()
            self._httpd_server.close()

    def kqueue_server_forever(self):
        try:
            kq = select.kqueue()
            change_kevent = select.kevent(self._httpd_server.fileno(),
                                          filter=select.KQ_FILTER_READ,
                                          flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT)
            while True:
                registered_events = kq.control([change_kevent], 1, self._timeout)
                for event in registered_events:
                    if event.filter == select.KQ_EV_EOF:
                        new_event = select.kevent(event.ident, flags=select.KQ_EV_CLEAR)
                        kq.control([new_event], 0, 0)
                    else:
                        cl, _ = self._httpd_server.accept()
                        with ThreadPoolExecutor(max_workers=self._thr_count) as executor:
                            worker = ThreadingEcho(cl, self._processor)
                            executor.submit(worker.handle_connection())
        finally:
            kq.close()
            self._httpd_server.close()


class ThreadingEcho:
    def __init__(self, client, processor):
        self.client = client
        self._processor = processor

    def handle_connection(self):
        """
                Handle each client socket. ~ data on it and processing data send
                back to the client. If there are no more data
                available on the read side, shutdown and close the
                socket.
            """
        buf = b''
        try:
            while True:
                recv = self.client.recv(DEFAULT_BUFFSIZE)
                buf += recv
                if buf.endswith(b'\r\n') or buf.endswith(b'\n'):
                    break
            message = self._processor(buf)
            self.send_all(message)
            self.client.close()
            if isinstance(self.client, dict):
                del self.client
        except error as e:
            if error.errno == 35:
                logging.error(e)
                return True
            elif error.errno == 57:
                logging.error(e)
                return True
            else:
                logging.error(e)
                pass

    def send_all(self, message, timeout=DEFAULT_TIMEOUT):
        # Sender byte by byte
        content_length = len(message)
        bt = self.client.send(message)
        time.sleep(timeout)
        while bt < content_length:
            bt += self.client.send(message[bt:])


def http_processor(request, date=DATE, document_root=''):
    # Accept the browser sent me the http request
    try:
        request_str = request.decode('utf-8')
        req, header_alone = http_req_line_parser(request_str)
        req_header = http_parse_header(header_alone)
        method, target, ver = http_parse_request_line(req)
        file_name = http_parse_file_name(unquote(target))
        path = "./" + document_root + "/" + file_name
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
    if re.findall(r'/\.\.', unquote(target)):
        raise HTTPError(400, 'Bad request', 'Too long path name')
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


def main():
    op = OptionParser()
    op.add_option("-w", "--worker", action="store", type=str, help="Setup worker count",
                  default=2)
    op.add_option("-g", "--logdir", action="store", type=str, help="From where will be processed logs",
                  default='.')
    op.add_option("-l", "--log", action="store", type=str, help="Log filename.", default="app_webserver.log")
    (opts, args) = op.parse_args()
    logging.basicConfig(filename=opts.log,
                        filemode='w',
                        format='[%(asctime)s] %(levelname).1s %(message)s',
                        datefmt='%Y.%m.%d %H:%M:%S')

    httpd = MyHTTPServer("0.0.0.0", 8080, "Myserver")
    httpd_server = httpd.http_server_init()
    poller = PollQueue(httpd_server, http_processor, 1)
    # Choose OS
    if "darwin" == platform:
        logging.info("Starting webserver...")
        poller.kqueue_server_forever()
    logging.info("Starting webserver...")
    poller.epoll_serve_forever()


if __name__ == '__main__':
    sys.exit(main())
