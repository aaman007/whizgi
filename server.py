import socket
import signal
import errno
import sys
import io
import os
import datetime
import argparse


def grim_reaper(signum, frame):
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except OSError:
            return
        if pid == 0:
            return


class WSGIServer:
    ADDRESS_FAMILY = socket.AF_INET
    SOCKET_TYPE = socket.SOCK_STREAM
    REQUEST_QUEUE_SIZE = 1024

    def __init__(self, server_address):
        self.listen_socket = listen_socket = socket.socket(
            WSGIServer.ADDRESS_FAMILY,
            WSGIServer.SOCKET_TYPE,
        )
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_socket.bind(server_address)
        listen_socket.listen(WSGIServer.REQUEST_QUEUE_SIZE)
        host, port = listen_socket.getsockname()[:2]

        self.server_name = socket.getfqdn(host)
        self.server_port = port
        self.headers_set = []
        self.application = None
        self.request_count = 0

    @staticmethod
    def _get_current_datetime():
        dt = datetime.datetime.utcnow()
        return dt.strftime('%a, %d %b %Y %X UTC')

    def set_app(self, application):
        self.application = application

    def serve_forever(self):
        signal.signal(signal.SIGCHLD, grim_reaper)
        listen_socket = self.listen_socket

        while True:
            self.request_count += 1
            request_number = self.request_count

            try:
                connection, client_address = listen_socket.accept()
                print(f'Recieved request #{request_number}')
            except IOError as e:
                code, msg = e.args
                if code == errno.EINTR:
                    continue
                else:
                    raise

            print(f'Forking for request #{request_number}')
            pid = os.fork()
            if pid == 0:
                print(f'Handling request #{request_number} in child process')
                listen_socket.close()  # close child copy
                self.handle_request(connection, client_address)
                connection.close()  # close child copy
                print(
                    f'Closed connection for request #{request_number} in child process')
                os._exit(0)
            else:
                connection.close()  # close parent copy
                print(
                    f'Closed connection for request #{request_number} in parent process')

    def handle_request(self, connection, client_address):
        request_data = connection.recv(1024)
        request_data = request_data.decode('utf-8')

        # print(':::request_data:::')
        # print(''.join(f'< {line}\n' for line in request_data.splitlines()))

        request_method, request_path, _ = self.parse_request(
            request_data
        )
        environ = self.get_environ(
            request_data,
            request_method,
            request_path,
        )

        result = self.application(environ, self.start_response)
        self.finish_response(result, connection)

    def parse_request(self, text):
        request_line = text.splitlines()[0]
        request_line = request_line.rstrip('\r\n')
        request_method, request_path, request_version = request_line.split()
        return request_method, request_path, request_version

    def start_response(self, status, request_headers, exc_info=None):
        server_headers = [
            ('Date', self._get_current_datetime()),
            ('Server', 'WSGIServer 0.2'),
        ]
        self.headers_set = [status, request_headers + server_headers]

    def finish_response(self, result, connection):
        try:
            status, response_headers = self.headers_set
            response = f'HTTP/1.1 {status}\r\n'

            for header in response_headers:
                response += '{0}: {1}\r\n'.format(*header)
            response += '\r\n'
            for data in result:
                response += data.decode('utf-8')

            # print(':::response data:::')
            # print(''.join(f'> {line}\n' for line in response.splitlines()))

            response_bytes = response.encode()
            connection.sendall(response_bytes)
        finally:
            connection.close()

    def get_environ(self, request_data, request_method, request_path):
        environ = {}

        # Required WSGI variables
        environ['wsgi.version'] = (1, 0)
        environ['wsgi.url_scheme'] = 'http'
        environ['wsgi.input'] = io.StringIO(request_data)
        environ['wsgi.errors'] = sys.stderr
        environ['wsgi.multithread'] = False
        environ['wsgi.multiprocess'] = False
        environ['wsgi.run_once'] = False

        # Required CGI variables
        environ['REQUEST_METHOD'] = request_method
        environ['PATH_INFO'] = request_path
        environ['SERVER_NAME'] = self.server_name
        environ['SERVER_PORT'] = str(self.server_port)

        return environ


def make_server(host, port, application):
    server = WSGIServer((host, port))
    server.set_app(application)
    return server


def wsgi_app_path(wsgi_app):
    if wsgi_app.count(':') != 1:
        raise ValueError()
    module, application = wsgi_app.split(':')
    if not module or not application:
        raise ValueError()
    return module, application


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process configuration')
    parser.add_argument(
        '-a',
        '--wsgi-app',
        dest='wsgi_app',
        type=wsgi_app_path,
        help='wsgi application location in form module:callable',
        required=True,
    )
    parser.add_argument(
        '-H',
        '--host',
        dest='host',
        type=str,
        default='127.0.0.1',
        help='host name or ip address',
    )
    parser.add_argument(
        '-p',
        '--port',
        dest='port',
        type=int,
        default=8000,
        help='port for the WSGI application',
    )
    args = parser.parse_args()
    module, application = args.wsgi_app
    module = __import__(module)
    application = getattr(module, application)
    server = make_server(args.host, args.port, application)
    print(f'WSGIServer: Serving HTTP on http://{args.host}:{args.port} ...\n')
    server.serve_forever()
