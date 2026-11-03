"""Small RESP2 transport. Secrets stay in socket data, never process arguments."""
import socket


class RedisError(RuntimeError):
    pass


def text(value):
    return value.decode() if isinstance(value,bytes) else str(value)


class Client:
    def __init__(self, password, username='default', port=6379, timeout=None):
        self.socket = socket.create_connection(('127.0.0.1', port), timeout=timeout)
        self.file = self.socket.makefile('rb')
        try:
            self.command('AUTH', username, password)
        except Exception:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.file.close()
        self.socket.close()

    def read(self):
        line = self.file.readline()
        if not line.endswith(b'\r\n'):
            raise ConnectionError('Invalid service reply')
        kind, value = line[:1], line[1:-2]
        if kind == b'+':
            return value.decode()
        if kind == b'-':
            # Do not put server-controlled strings in an externally visible error.
            raise RedisError('Dragonfly rejected the operation')
        if kind == b':':
            return int(value)
        if kind == b'$':
            size = int(value)
            if size == -1:
                return None
            if size < 0:
                raise ConnectionError('Service reply too large')
            data = self.file.read(size)
            if len(data) != size or self.file.read(2) != b'\r\n':
                raise ConnectionError('Incomplete service reply')
            return data
        if kind == b'*':
            size = int(value)
            if size == -1:
                return None
            if size < 0:
                raise ConnectionError('Service reply too large')
            return [self.read() for _ in range(size)]
        raise ConnectionError('Unknown service reply')

    def command(self, *args):
        parts = [arg if isinstance(arg, bytes) else str(arg).encode() for arg in args]
        self.socket.sendall(b'*'+str(len(parts)).encode()+b'\r\n'+b''.join(
            b'$'+str(len(arg)).encode()+b'\r\n'+arg+b'\r\n' for arg in parts))
        return self.read()
