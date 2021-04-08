import logging
import sys
import time
from datetime import datetime
from email.parser import Parser
from optparse import OptionParser
from socket import socket, error, \
    AF_INET, SOCK_STREAM, \
    SOL_SOCKET, SO_REUSEADDR, \
    SHUT_WR
import re
from urllib.parse import unquote
from sys import platform
import select

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

DEFAULT_TIMEOUT = 0.1

DEFAULT_BUFFSIZE = 1024


class MyHTTPServer:
    def __init__(self, host, port, server_name, timeout=DEFAULT_TIMEOUT):
        self._host = host
        self._port = port
        self._server_name = server_name
        self._document_root = ''
        self._buffsize = DEFAULT_BUFFSIZE
        self._date = datetime.now().strftime("%a %d %b %Y, %H:%M:%S GMT")
        self._response_body = DEFAULT_ERROR_MESSAGE
        self._timeout = timeout

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
        http_server.listen(1)
        # Set the socket is blocked manner
        http_server.setblocking(False)
        return http_server

    def epoll_serve_forever(self, response=None):
        http_server = self.http_server_init()
        # Create an epoll objects
        epl = select.epoll()
        # Corresponding to the listening socket fd (file descriptor) registered to the epoll
        epl.register(http_server.fileno(), select.EPOLLIN)
        logging.info("FD {fd} registred in epoll".format(fd=http_server.fileno()))
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
                    if fd == http_server.fileno():
                        client, info = http_server.accept()
                        client.setblocking(False)
                        # The new socket is registered in epoll
                        epl.register(client.fileno(), select.EPOLLIN)
                        # The correspondence between file descriptors and sockets into dictionary
                        fd_event_dict[client.fileno()] = client
                        requests[client.fileno()] = b''
                        responses[client.fileno()] = response
                    elif event == select.EPOLLIN:
                        # Judge whether a socket connected data sent me
                        result = self.handle_connection(fd_event_dict[fd])
                        # recv_data = fd_event_dict[fd].recv(self._buffsize).decode("utf-8")
                        # if recv_data:
                        #     resposne = self.process_request(recv_data)
                        #     fd_event_dict[fd].send(resposne.encode("utf-8"))
                        if result:
                            fd_event_dict[fd].close()
                            # epl.unregister(fd)
                            del fd_event_dict[fd]
        finally:
            epl.unregister(http_server.fileno())
            epl.close()
            http_server.close()

    def kqueue_server_forever(self):
        try:
            http_server = self.http_server_init()
            kq = select.kqueue()
        # Initialise the master fd(s.fileno()) from server socket
        # kq_fd = select.kqueue.fromfd(kq.fileno())
        # change_kevent = select.kevent(http_server.fileno(),
        #                        filter=select.KQ_FILTER_READ,  # we are interested in reads
        #                        flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE)
            change_kevent = select.kevent(http_server.fileno(),
                                      filter=select.KQ_FILTER_READ,
                                      flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT)
            while True:
                registered_events = kq.control([change_kevent], 1, self._timeout)
                for event in registered_events:
                    if (event.filter == select.KQ_EV_EOF):
                        new_event = select.kevent(event.ident, flags=select.KQ_EV_CLEAR)
                        kq.control([new_event], 0, 0)
                    else:
                        cl, _ = http_server.accept()
                        result = self.handle_connection(cl)
                        if result:
                            cl.close()
        finally:
            kq.close()
            http_server.close()

    def handle_connection(self, cl_socket):
        """
                Handle each client socket. ~ data on it and processing data send
                back to the client. If there are no more data
                available on the read side, shutdown and close the
                socket.
            """
        buf = b''
        try:
            while True:
                recv = cl_socket.recv(self._buffsize)
                buf += recv
                if buf.endswith(b'\r\n') or buf.endswith(b'\n'):
                    break
            header, body = self.process_request(buf)
            send = self.send_all(cl_socket, header, body)
            return send
        except error as e:
            if str(e) == "[Errno 35] Resource temporarily unavailable":
                logging.error(e)
                time.sleep(0.1)
            elif str(e) == "[Errno 57] Socket is not connected":
                logging.error(e)
                return True
            else:
                logging.error(e)
                pass

    def send_all(self, cl_socket, header, body):
        # Sender byte by byte
        if body:
            message = header + b'\r\n' + body + b'\r\n'
        else:
            message = header + b'\r\n'
        content_length = len(message)
        bt = cl_socket.send(message)
        while bt < content_length:
            bt += cl_socket.send(message[bt:])
        return True if bt == content_length else False

    def process_request(self, request: str):
        # Accept the browser sent me the http request
        try:
            request_str = request.decode('utf-8')
            req_header = self.parse_header(request_str)
            method, target, ver = self.parse_request_line(request_str)
            file_name, content_type = self.parse_file_name(unquote(target))
            path = "./" + self._document_root + "/" + file_name
            header, body = self.method_choose(method, path, self._date, req_header, content_type)
            response = header, body
            return response
        except Exception as e:
            if hasattr(e, 'status'):
                err = HTTPError(e.status, e.reason, e.body, self._date, req_header['Host'])
                logging.error("ERROR Occured status - {}, reason - {}, date - {}, host - {}".format(e.status,
                                                                                                    e.reason,
                                                                                                    self._date,
                                                                                                    req_header['Host']))
            else:
                err = HTTPError('405', 'Method Not Implemented', 'Request Error', self._date)
                logging.error("ERROR Occured status - 405, reason - Method Not Implemented, date - {}".format(self._date))
            return err.error_content()

    @staticmethod
    def method_choose(method, path, date, header, content_type):
        # Returns http response
        try:
            if 'image' or 'application' in content_type:
                with open(path, "rb") as f:
                    body = f.read()
            else:
                with open(path, "r") as f:
                    body = f.read().encode("utf-8")
            header = HEADER.format(code='200',
                                   explain='OK',
                                   date=date,
                                   servername=header.get("Host"),
                                   length=len(body),
                                   type=content_type,
                                   conn='Close').encode("utf-8")
            if method == 'head':
                return header, None
            return header, body
        except:
            raise HTTPError(404, 'Not Found')

    def parse_file_name(self, request_line):
        # Splitting request line for looking up path, filename and content_type
        self.match_lagrge_name_path(request_line)
        if "?" in request_line:
            parsed_url, args = request_line.split("?")
            parsed_url = parsed_url.split("/")
        else:
            parsed_url = request_line.split('/')
        if parsed_url[-1] == "":
            file_name = '/'.join(parsed_url[1:])
            file_name += "index.html"
            content_type = MIME["html"]
        else:
            file_name = '/'.join(parsed_url[1:])
            content_type = self.looking_acc_cont_type(parsed_url)
        return file_name, content_type

    @staticmethod
    def match_lagrge_name_path(path):
        match = re.findall(r'/\.\.', path)
        if match:
            raise HTTPError(400, 'Bad request', 'Too long path name')

    @staticmethod
    def looking_acc_cont_type(file_names):
        # looking for accepted files for content-type format
        *_, ext = file_names[-1].split('.')
        if ext not in MIME.keys():
            return 'Non implemented Content-type'
        return MIME[ext]

    @staticmethod
    def parse_header(line):
        # Parsing header messages
        _, headers_alone = line.split('\r\n', 1)
        return Parser().parsestr(headers_alone)

    def parse_request_line(self, request_line):
        # Analyze the first line of header
        req, _ = request_line.split('\r\n', 1)
        words = req.split()
        if len(words) != 3:
            raise HTTPError(400, 'Bad request', 'Malformed request line')
        method, target, ver = words
        if ver != 'HTTP/1.1':
            raise HTTPError(505, 'HTTP Version Not Supported')
        method = method.lower()
        if method not in ['get', 'head']:
            raise HTTPError(405, 'Method Not Allowed')
        return method, target, ver


class HTTPError(Exception):
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
        response = resposne_header, res_body
        return response


class Worker:
    def __init__(self, worker):
        self.worker = worker

    def start(self):
        http_server = MyHTTPServer("", 8080, "Myserver")
        if "darwin" == platform:
            logging.info("Starting webserver...")
            http_server.kqueue_server_forever()
        logging.info("Starting webserver...")
        http_server.epoll_serve_forever()


def main():
    op = OptionParser()
    op.add_option("-w", "--worker", action="store", type=str, help="Setup worker count",
                  default=1)
    op.add_option("-g", "--logdir", action="store", type=str, help="From where will be processed logs",
                  default='.')
    op.add_option("-l", "--log", action="store", type=str, help="Log filename.", default="app_webserver.log")
    (opts, args) = op.parse_args()
    logging.basicConfig(filename=opts.log,
                        filemode='w',
                        format='[%(asctime)s] %(levelname).1s %(message)s',
                        datefmt='%Y.%m.%d %H:%M:%S')
    work = Worker(opts.worker)
    work.start()




if __name__ == '__main__':
    sys.exit(main())
