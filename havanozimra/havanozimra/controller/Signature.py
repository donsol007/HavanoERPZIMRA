import base64
import hashlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import load_pem_private_key

class Signature:
    concate_data = ""

    @staticmethod
    def generate_base64_hash(input_str: str) -> str:
        sha256 = hashlib.sha256()
        sha256.update(input_str.encode('utf-8'))
        return base64.b64encode(sha256.digest()).decode('utf-8')

    @staticmethod
    def convert_pem_to_private_key(private_key_pem: str):
        private_key = load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None,
            backend=default_backend()
        )
        return private_key

    @staticmethod
    def sign_data(data: str, private_key_path: str) -> str:
        with open(private_key_path, 'r') as file:
            private_key_pem = file.read()

        private_key = Signature.convert_pem_to_private_key(private_key_pem)
        signed = private_key.sign(
            data.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return base64.b64encode(signed).decode('utf-8')

    @staticmethod
    def generate_signature(data: str, private_key_pem: str) -> str:
        private_key = Signature.convert_pem_to_private_key(private_key_pem)
        signed = private_key.sign(
            data.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return base64.b64encode(signed).decode('utf-8')

    @staticmethod
    def compute_hash(request: str) -> str:
        sha256 = hashlib.sha256()
        sha256.update(request.encode('utf-8'))
        return base64.b64encode(sha256.digest()).decode('utf-8')

    @staticmethod
    def concatenate_data(
        device_id: int,
        receipt_type: str,
        receipt_currency: str,
        receipt_global_no: str,
        receipt_date: str,
        receipt_total: float,
        receipt_taxes: str,
        previous_receipt_hash: str) -> str:
        str_total = str(receipt_total).replace(" ", "")
        Signature.concate_data = (
            str(device_id) +
            receipt_type +
            receipt_currency +
            receipt_global_no +
            receipt_date +
            str_total +
            str(receipt_taxes) +
            previous_receipt_hash
        )
        return Signature.concate_data
