import socket
import struct
import threading

from Crypto.PublicKey import ECC
from Crypto.Protocol.KDF import HKDF
from Crypto.Hash import SHA256
from Crypto.Cipher import AES

SEPARATOR = b'\0'
MSG_LEN_SIZE = 4  # bytes

def derive_key(point):
    x = int(point.x)
    blen = (point.size_in_bytes())
    raw = x.to_bytes(blen, "big")
    return HKDF(raw, 32, b"", SHA256, context=b"ecdh-aesgcm")

class Connection:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.cores = 4
        self.aes_key = None

    def __encode_field(self, field: bytes) -> bytes:
        if isinstance(field, str): field = field.encode('utf-8')
        elif isinstance(field, int): field = field.to_bytes(4, 'big')
        elif isinstance(field, float): field = bytearray(struct.pack("f", field))
        elif isinstance(field, bool): field = str(field).encode('utf-8')
        return field

    def get_aes(self) -> AES:
        return AES.new(self.aes_key, AES.MODE_EAX, nonce=b'0000000000000000') if self.aes_key else None

    def send_raw(self, data: bytes):
        self.conn.sendall(data)

    def receive_raw(self, bufsize=1024) -> bytes:
        data = b''
        while len(data) < bufsize:
            packet = self.conn.recv(bufsize - len(data))
            if not packet:
                return b''
            data += packet
        return data

    def _parse_fields(self, data: bytes, field_count: int = -1) -> list[bytes]:
        return data.split(SEPARATOR, field_count)

    def send_fields(self, fields: list[bytes]):
        data = SEPARATOR.join([self.__encode_field(field) for field in fields])
        if self.get_aes():
            ciphertext = self.get_aes().encrypt(data)
            data = b'AES' + SEPARATOR + ciphertext
        data = len(data).to_bytes(MSG_LEN_SIZE, 'big') + data
        self.send_raw(data)

    def receive_by_size(self) -> bytes:
        raw_msglen = self.receive_raw(MSG_LEN_SIZE)
        if not raw_msglen: return b''
        msglen = int.from_bytes(raw_msglen, 'big')
        return self.receive_raw(msglen)

    def receive_fields(self, field_limit=-1) -> tuple[bytes, list[bytes]]:
        data = self.receive_by_size()
        if not data: return b'', []
        if self.aes_key and data.startswith(b'AES'):
            fields = self._parse_fields(data, 1)
            if len(fields) != 2 : raise Exception("Invalid AES message format")
            if fields[0] != b'AES': raise Exception("Invalid AES message format")
            ciphertext = fields[1]
            data = self.get_aes().decrypt(ciphertext)

        if not data: return b'', []
        return data, self._parse_fields(data, field_limit)
        
    def connect(self):
        sk = ECC.generate(curve="P-256")
        server_pk = sk.public_key().export_key(format="DER")
        self.send_fields([b'HELLO', server_pk])

        raw, fields = self.receive_fields(2)  
        fields = (raw[0:5], raw[6:10], raw[11:])
        if fields[0] != b'HELLO': raise Exception("Invalid handshake from client")
        client_pk = ECC.import_key(fields[2])
        try:
            client_cores = int.from_bytes(fields[1], 'big')
            self.cores = client_cores
        except:
            print("Failed to parse client cores, using default 4")
            self.cores = 4

        shared = client_pk.pointQ * sk.d
        key = derive_key(shared)
        self.aes_key = key

        d, _ = self.receive_fields(1)
        if d != b'OK': raise Exception("AES handshake failed")

        self.send_fields([b'OK'])
        print(f"AES session established with {f'{self.addr[0]}:{self.addr[1]}'}")
        print("Shared key:", key.hex())
        print(f"Client cores: {self.cores}")
        print()

    def close(self):
        self.conn.close()

class SocketServer:
    def __init__(self, host='0.0.0.0', port=8080, listen=1000, callbacks: dict = {}):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections: list[Connection] = []
        self.callbacks = callbacks

        self.host = host
        self.port = port
        self.listen = listen

    def __handle_client(self, connection: Connection):
        while True:
            try:
                data, fields = connection.receive_fields()
                if not fields:
                    print(f"Connection closed by {connection.addr}")
                    self.disconnect(connection)
                    self.callbacks.get('on_disconnect', lambda conn: None)(connection)
                    break

                self.callbacks.get('on_message', lambda conn, raw, fields: None)(connection, data, fields)
            except Exception as e:
                print(f"Error with connection {connection.addr}: {e}")
                self.disconnect(connection)
                self.callbacks.get('on_disconnect', lambda conn: None)(connection)
                break
                

    def __connection_manager(self):
        while True:
            conn, addr = self.sock.accept()
            connection = Connection(conn, addr)
            self.connections.append(connection)
            print(f"New connection from {f'{addr[0]}:{addr[1]}'}")
            self.callbacks.get('on_connect', lambda conn: None)(connection)
            threading.Thread(target=self.__handle_client, args=(connection,), daemon=True).start()

    def start(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen(self.listen)
        print(f"Server listening on {self.host}:{self.port}")
        threading.Thread(target=self.__connection_manager, daemon=True).start()

    def stop(self):
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        print("Server stopped")

    def disconnect(self, connection: Connection):
        for conn in self.connections:
            if conn == connection:
                conn.close()
                self.connections.remove(connection)
                print(f"Disconnected {connection.addr}")