import os
import xml.etree.ElementTree as ET
from decimal import Decimal

class ZReport:
    def __init__(self):
        self.directory_zreport = os.getenv("PROGRAMDATA") or os.environ.get("APPDATA")
        self.directory_name = os.path.dirname(os.path.abspath(__file__))

    def get_data_from_ini(self, key):
        # Placeholder for INI reader logic
        # Replace this with actual INI reading logic as needed
        return "DEVICE_SERIAL_NO"

    def create_zreport(self, receipt_type, currency, daily_total, vatable_net_amount, vatable_tax, non_vatable_net):
        serial_no = self.get_data_from_ini("deviceSerialNo")
        file_path = os.path.join(self.directory_zreport, "HavanoZimra", serial_no, "zreport.hrpt")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        if os.path.exists(file_path):
            tree = ET.parse(file_path)
            root = tree.getroot()
        else:
            root = ET.Element("ZREPORT")

        parent_element = root.find(receipt_type)
        if parent_element is None:
            parent_element = ET.SubElement(root, receipt_type)

        currency_element = None
        for elem in parent_element.findall("Currency"):
            if elem.find("Name") is not None and elem.find("Name").text == currency:
                currency_element = elem
                break

        if receipt_type == "FISCALINVOICE":
            if non_vatable_net > 0:
                vatable_net_amount = daily_total - non_vatable_net

            if currency_element is None:
                currency_element = ET.SubElement(parent_element, "Currency")
                ET.SubElement(currency_element, "Name").text = currency
                ET.SubElement(currency_element, "DailyTotal").text = f"{daily_total:.2f}"
                ET.SubElement(currency_element, "VatableNetAmount").text = f"{vatable_net_amount:.2f}"
                ET.SubElement(currency_element, "VatableTax").text = f"{vatable_tax:.2f}"
                ET.SubElement(currency_element, "NonVatableNet").text = f"{non_vatable_net:.2f}"
            else:
                currency_element.find("DailyTotal").text = f"{Decimal(currency_element.find('DailyTotal').text) + daily_total:.2f}"
                currency_element.find("VatableNetAmount").text = f"{Decimal(currency_element.find('VatableNetAmount').text) + vatable_net_amount:.2f}"
                currency_element.find("VatableTax").text = f"{Decimal(currency_element.find('VatableTax').text) + vatable_tax:.2f}"
                currency_element.find("NonVatableNet").text = f"{Decimal(currency_element.find('NonVatableNet').text) + non_vatable_net:.2f}"
        else:
            # CREDITNOTE
            if abs(non_vatable_net) > 0:
                vatable_net_amount = -(abs(daily_total) - abs(non_vatable_net))
                print(non_vatable_net)

            if currency_element is None:
                currency_element = ET.SubElement(parent_element, "Currency")
                ET.SubElement(currency_element, "Name").text = currency
                ET.SubElement(currency_element, "DailyTotal").text = f"{daily_total:.2f}"
                ET.SubElement(currency_element, "VatableNetAmount").text = f"{vatable_net_amount:.2f}"
                ET.SubElement(currency_element, "VatableTax").text = f"{vatable_tax:.2f}"
                ET.SubElement(currency_element, "NonVatableNet").text = f"{non_vatable_net:.2f}"
            else:
                currency_element.find("DailyTotal").text = f"{Decimal(currency_element.find('DailyTotal').text) + daily_total:.2f}"
                currency_element.find("VatableNetAmount").text = f"{Decimal(currency_element.find('VatableNetAmount').text) + vatable_net_amount:.2f}"
                currency_element.find("VatableTax").text = f"{Decimal(currency_element.find('VatableTax').text) + vatable_tax:.2f}"
                currency_element.find("NonVatableNet").text = f"{Decimal(currency_element.find('NonVatableNet').text) + non_vatable_net:.2f}"

        # Save the updated XML
        tree = ET.ElementTree(root)
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
