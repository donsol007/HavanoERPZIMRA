import hashlib
import base64

class ReceiptQRCodes:
    receipt_data = ""

    @staticmethod
    def generate_qr_code(qr_url, device_id, receipt_date, receipt_global_no, receipt_qr_data):
        receipt_qr_data = ReceiptQRCodes.get_md5_hash(ReceiptQRCodes.convert_to_hex(receipt_qr_data), 16)
        device_id = ReceiptQRCodes.pad_left(device_id, 10)
        receipt_global_no = ReceiptQRCodes.pad_left(receipt_global_no, 10)
        return ReceiptQRCodes.concatenate_data(qr_url,device_id, receipt_date, receipt_global_no, receipt_qr_data.upper())

    @staticmethod
    def generate_verification_code(device_signature):
        device_signature = ReceiptQRCodes.get_md5_hash(ReceiptQRCodes.convert_to_hex(device_signature), 16)
        return ReceiptQRCodes.format_data(device_signature.upper(), '-', 4)

    @staticmethod
    def format_data(input_string, separator, group_size):
        formatted = []
        for i, c in enumerate(input_string):
            formatted.append(c)
            if (i + 1) % group_size == 0 and i != len(input_string) - 1:
                formatted.append(separator)
        return ''.join(formatted)

    @staticmethod
    def concatenate_data(qr_url, device_id, receipt_date, receipt_global_no, receipt_qr_data):
        ReceiptQRCodes.receipt_data = f"{qr_url}{device_id}{receipt_date}{receipt_global_no}{receipt_qr_data}"
        return ReceiptQRCodes.receipt_data

    @staticmethod
    def get_md5_hash(hex_string, length):
        byte_array = bytes.fromhex(hex_string)
        md5_hash = hashlib.md5(byte_array).hexdigest().upper()
        return md5_hash[:length]

    @staticmethod
    def group_data(hex_string):
        return bytes.fromhex(hex_string)

    @staticmethod
    def convert_string_to_hex(input_string):
        return ''.join(f"{b:02X}" for b in input_string.encode('utf-8'))

    @staticmethod
    def convert_to_hex(base64_string):
        raw_bytes = base64.b64decode(base64_string)
        return ''.join(f"{b:02X}" for b in raw_bytes)

    @staticmethod
    def pad_left(string_input, total_length):
        return string_input.zfill(total_length)
