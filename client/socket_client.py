import multiprocessing
import socket
import struct
import sys
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

class SocketClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.aes_key = None

    def get_aes(self):
        return AES.new(self.aes_key, AES.MODE_EAX, nonce=b'0000000000000000') if self.aes_key else None

    def __encode_field(self, field: any) -> bytes:
        if isinstance(field, str): field = field.encode('utf-8')
        elif isinstance(field, int): field = field.to_bytes(4, 'big')
        elif isinstance(field, float): field = bytearray(struct.pack("f", field))
        elif isinstance(field, bool): field = str(field).encode('utf-8')
        return field

    def connect(self):
        self.sock.connect((self.host, self.port))
        print(f"Connected to server at {self.host}:{self.port}")

    def receive_raw(self, bufsize=1024) -> bytes:
        return self.sock.recv(bufsize)
    
    def send_raw(self, data: bytes):
        self.sock.sendall(data)

    def receive_by_size(self) -> bytes:
        raw_msglen = self.receive_raw(MSG_LEN_SIZE)
        if not raw_msglen: return b''
        msglen = int.from_bytes(raw_msglen, 'big')
        return self.receive_raw(msglen)
    
    def _parse_fields(self, data: bytes, field_count: int = -1) -> list[bytes]:
        return data.split(SEPARATOR, field_count)

    def receive_fields(self, field_limit=-1) -> (bytes, list[bytes]):
        data = self.receive_by_size()
        if not data: return b'', []
        if self.aes_key and data.startswith(b'AES'):
            fields = data.split(SEPARATOR, 1)
            if len(fields) != 2 : raise Exception("Invalid AES message format")
            if fields[0] != b'AES': raise Exception("Invalid AES message format")
            ciphertext = fields[1]
            data = self.get_aes().decrypt(ciphertext)

        if not data: return b'', []
        return data, self._parse_fields(data, field_limit)

    def send_fields(self, fields: list[bytes]):
        data = SEPARATOR.join([self.__encode_field(field) for field in fields])
        if self.get_aes():
            ciphertext = self.get_aes().encrypt(data)
            data = b'AES' + SEPARATOR + ciphertext
        data = len(data).to_bytes(MSG_LEN_SIZE, 'big') + data
        self.send_raw(data)

    def handshake(self):
        _, fields = self.receive_fields(1)
        if fields[0] != b'HELLO': raise Exception("Invalid handshake from server")
        server_pk = ECC.import_key(fields[1])
        sk = ECC.generate(curve="P-256")
        client_pk = sk.public_key().export_key(format="DER")
        core_count = multiprocessing.cpu_count()
        self.send_fields([b'HELLO', core_count, client_pk])

        shared_point = server_pk.pointQ * sk.d
        key = derive_key(shared_point)
        self.aes_key = key
        print("Shared key:", key.hex())

        self.send_fields([b'OK'])

        data, _ = self.receive_fields()
        if data != b'OK': raise Exception("AES handshake failed")

        print("AES session established with server")