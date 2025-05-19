import asyncio
import httpx
from pathlib import Path
import ssl
import os
import json
from configparser import ConfigParser
from enum import Enum
import datetime
from xml.etree import ElementTree as ET
from havanozimra.havanozimra.controller.InvoiceData import( receiptWrapper, ReceiptLine, ReceiptTax, CreditDebitNote,
    BuyerData, BuyerContacts, BuyerAddress ) 
from havanozimra.havanozimra.controller.CloseDay import (FiscalCounter,FiscalDay,FiscalDayDeviceSignature)
from typing import List
from havanozimra.havanozimra.controller.ReceiptQRCodes import ReceiptQRCodes
from havanozimra.havanozimra.controller.Signature import Signature
import aiohttp
from dataclasses import asdict
from datetime import datetime
import qrcode
import base64
from io import BytesIO
import random
import frappe
from frappe import _, msgprint, throw
import time

_config = ConfigParser()
_config.read("havanoconfig.ini")

class ReqType(Enum):
    GlobalNo = 1
    Status    = 2
    Config    = 3
    Ping      = 4

def get_config_value(fieldname: str) -> str:
    try:
        doctype ="Zimra Account"
        value = frappe.db.get_single_value(doctype, fieldname)
        return value
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),f"Error fetching {fieldname} from {doctype}: {e}")
        return None
    
def update_config_value(fieldname: str, value: str):
    doctype ="Zimra Account"
    try:
        frappe.db.set_single_value(doctype, fieldname, value)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),f"Error updating {fieldname} in {doctype}: {e}")


def get_pem_cert_path() -> str:
    site_path = frappe.get_site_path()
    file_path = get_config_value("account_cert")
    full_path = os.path.join(site_path, file_path.lstrip('/'))
    return full_path

def get_private_key_path() -> str:
    site_path = frappe.get_site_path()
    file_path = get_config_value("account_key")
    full_path = os.path.join(site_path, file_path.lstrip('/'))
    return full_path


#=======CHECK INTERNET CONNECTION============
def is_internet_available():
    try:
        with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            with session.get("http://www.google.com") as response:
                return response.status == 200
    except Exception:
        return False
#=========== UPDATE TAX ITEM ===============   

def add_or_update_tax_item(invoice_flag, taxes_item_list, tax_code, tax_percent, tax_id, sales_amount_with_tax, tax_amount, vat_type):
    existing_item = next((item for item in taxes_item_list if item.taxCode == tax_code), None)

    if existing_item:
        if invoice_flag == 1:
            existing_item.salesAmountWithTax = -(abs(existing_item.salesAmountWithTax) + sales_amount_with_tax)
            existing_item.taxAmount = -(abs(existing_item.taxAmount) + tax_amount)
        else:
            existing_item.salesAmountWithTax += sales_amount_with_tax
            existing_item.taxAmount += tax_amount
    else:
        if invoice_flag == 1:
            if vat_type == "EXEMPT":
                new_item = ReceiptTax(
                    taxCode=tax_code,
                    taxID=tax_id,
                    taxPercent=None,
                    salesAmountWithTax=-sales_amount_with_tax,
                    taxAmount=-tax_amount
                )
            else:
                new_item = ReceiptTax(
                    taxCode=tax_code,
                    taxPercent=tax_percent,
                    taxID=tax_id,
                    salesAmountWithTax=-sales_amount_with_tax,
                    taxAmount=-tax_amount
                )
        else:
            if vat_type == "EXEMPT":
                new_item =  ReceiptTax(
                    taxCode=tax_code,
                    taxID=tax_id,
                    taxPercent=None,
                    salesAmountWithTax=sales_amount_with_tax,
                    taxAmount=tax_amount
                )
            else:
                new_item = ReceiptTax(
                    taxCode=tax_code,
                    taxPercent=tax_percent,
                    taxID=tax_id,
                    salesAmountWithTax=sales_amount_with_tax,
                    taxAmount=tax_amount
                )
        taxes_item_list.append(new_item)
        
def create_fiscal_day_json(fiscal_day_no, fiscal_day_opened):
    if fiscal_day_no == "0":
        fiscal_day_no = "1"
    else:
        fiscal_day_no = str(int(fiscal_day_no) + 1)
    data = {
        "fiscalDayNo": fiscal_day_no,
        "fiscalDayOpened": fiscal_day_opened
    }
    return json.dumps(data)

#========= SEND INVOICE TO ZIMRA ===========
def send_to_zimra(my_data: str, url: str) -> str:
    
    base_url = get_config_value("server_url")
    device_id = get_config_value("device_id")
    zimra_url = f"{base_url}/Device/v1/{device_id}{url}"
    #print(zimra_url)
    result = ""
    
    try:
        headers = {
            "accept": "application/json",
            "DeviceModelName": "Server",
            "DeviceModelVersion": "v1",
            "Content-Type": "application/json"
        }
        # prepare SSL context with your .pfx certificate
        ssl_ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        ssl_ctx.load_cert_chain(certfile=get_pem_cert_path(), keyfile=get_private_key_path())
        
        with httpx.Client(verify=ssl_ctx) as client:
            response =  client.post(zimra_url, data=my_data, headers=headers)

            if response.status_code == 200:
                # Logging examples
                frappe.log_error(frappe.get_traceback(),"Receipt Submitted" )
                result = "Success"
            else:
                frappe.log_error(frappe.get_traceback() +  "\n" + response.text,"Receipt Submission Failed")
                result = "Failed"
    except Exception as ex:
        #print(ex)
        frappe.log_error(frappe.get_traceback(),f"Error sending Invoice: {ex}")
        result = "Failed"

    return result
#======== SEND PRIVATE REQUEST =============
def send_private_request(my_req_type: ReqType, req_method: str) -> str:

    base_url = get_config_value("server_url")
    result = ""
    # select endpoint based on request type
    endpoints = {
        ReqType.GlobalNo: "Device/v1/{}/GetStatus",
        ReqType.Status:   "Device/v1/{}/GetStatus",
        ReqType.Config:   "Device/v1/{}/GetConfig",
        ReqType.Ping:     "Device/v1/{}/Ping",
    }
    device_id = get_config_value("device_id")
    url_endpoint = endpoints[my_req_type].format(device_id)
    full_url = base_url.rstrip("/") + "/" + url_endpoint.lstrip("/")

    # prepare SSL context with your .pfx certificate
    ssl_ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    ssl_ctx.load_cert_chain(certfile=get_pem_cert_path(), keyfile=get_private_key_path())

    headers = {
        "accept": "application/json",
        "DeviceModelName": "Server",
        "DeviceModelVersion": "v1",
    }

    try:
        
        with httpx.Client(verify=ssl_ctx) as client:
            resp =  client.request(req_method,full_url, headers=headers)

        text = resp.text
        #frappe.log_error(frappe.get_traceback(),f"Response from {full_url}: {text}")
        
        if resp.is_success:
            payload = resp.json()

            if my_req_type == ReqType.GlobalNo:
                frappe.log_error(frappe.get_traceback(),"GlobalNo Request sent")
                return text

            elif my_req_type == ReqType.Status:
                frappe.log_error(frappe.get_traceback(),"Status Request sent")
                day_status = payload.get("fiscalDayStatus", "")
                return day_status

            elif my_req_type == ReqType.Config:
                frappe.log_error(frappe.get_traceback(),"Config Information requested")
                taxes = payload.get("applicableTaxes", [])
                result = [{"taxName": tax["taxName"],"taxID": tax["taxID"],"taxPercent": tax.get("taxPercent")} for tax in taxes]
                for tax in result:
                    tax_id   = str(tax.get("taxID", ""))
                    tax_pct  = tax.get("taxPercent")
                    print(tax_pct)
                    if tax_pct is None:
                        update_config_value("taxe", tax_id)
                    if str(tax_pct) == "0.0":
                        update_config_value("tax0", tax_id)
                    if str(tax_pct) == "15.0":
                        update_config_value("tax15", tax_id)
                    if str(tax_pct) == "5.0":
                        update_config_value("tax5", tax_id)
                return text

            elif my_req_type == ReqType.Ping:
                frappe.log_error(frappe.get_traceback(),"Ping Request sent")
                return text

        else:
            frappe.log_error(frappe.get_traceback(),f"Request failed: {resp.status_code} {resp.reason_phrase}")
            return resp.reason_phrase

    except Exception as ex:
        frappe.log_error(frappe.get_traceback(),f"An error occurred in send_private_request: {ex}")
        return "An unexpected error occurred"

#========= OPEN FISCAL DAY ============
@frappe.whitelist()
def openday(docname):
    
    msg = send_private_request(ReqType.Config, "GET")
    time.sleep(8)

    resp = open_fiscal_day()
    time.sleep(6)
    return resp
    #frappe.throw(msg)


    
def open_fiscal_day() -> str:
    base_url = get_config_value("server_url")
    result = ""
    
    try:
        fdate = datetime.now()
        open_date = fdate.strftime("%Y-%m-%dT%H:%M:%S")
        Openday_Data = create_fiscal_day_json(get_config_value("fiscal_day"), open_date)
        if not Openday_Data:
            return json.dumps("No Data found for Openday Request")

        zimra_url = f"{base_url}/Device/v1/{get_config_value('device_id')}/OpenDay"

        # build SSL context and load your PFX
        ssl_ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        ssl_ctx.load_cert_chain(certfile=get_pem_cert_path(), keyfile=get_private_key_path())

        headers = {
            "accept": "application/json",
            "DeviceModelName": "Server",
            "DeviceModelVersion": "v1",
            "Content-Type": "application/json"
        }

        with httpx.Client(verify=ssl_ctx) as client:
            response =  client.post(zimra_url,data=Openday_Data,headers=headers)

        # log raw response
        #frappe.log_error(frappe.get_traceback(),"Raw response: %s", response.text)
        openday_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        if response.is_success:
            payload = response.json()
            fiscal_day = str(payload["fiscalDayNo"])
            update_config_value("fiscal_day", fiscal_day)
            update_config_value("receiptcounter", "0")
            update_config_value("previous_receipt_hash", "")
            update_config_value("fiscal_date", openday_date)
            update_config_value("fiscaldaystatus", "FiscalDayOpened")

            result = f"Fiscal Day {fiscal_day} Successfully Opened"
            frappe.log_error(frappe.get_traceback(),"Open Fiscal Day request success")
            #frappe.log_error(frappe.get_traceback(),"Request status %s", result)
        else:
            detail = response.json().get("detail", "")
            frappe.log_error(frappe.get_traceback(),"Open Fiscal Day request failed")
            #frappe.log_error(frappe.get_traceback(),"Request status %s", detail)
            result = detail
    except Exception as ex:
        result = "Failed"
        frappe.log_error(frappe.get_traceback(),"Open Fiscal Day Error: %s", ex)

    return result
#=======VALIDATE XML STRING==========
def validate_xml_structure(xml_root: ET.Element) -> str:
    # Validate the root element
    if xml_root.tag != "ITEMS":
        return "Root element must be <ITEMS>."
    # Validate the presence of ITEM elements
    item_nodes = xml_root.findall("ITEM")
    if not item_nodes:
        return "At least one <ITEM> element is required."

    # Validate the presence of necessary child elements in each ITEM
    required_fields = ["ITEMCODE", "ITEMNAME", "HH", "QTY", "PRICE", "VATR", "VAT", "TOTAL"]
    for item in item_nodes:
        missing_fields = [field for field in required_fields if item.find(field) is None]
        if missing_fields:
            return "Each <ITEM> element must contain elements: ITEMCODE, ITEMNAME, QTY, PRICE, VATR, VAT, TOTAL."

    return ""  # Return empty string if no validation issues
#=========CALCULATE TAX AMOUNT ============
def calculate_tax_amount(price_including_tax: float, tax_percent: float) -> float:
    tax_rate = tax_percent / 100
    tax_amount = price_including_tax * tax_rate / (1 + tax_rate)
    return tax_amount

def format_to_two_decimals(value):
    if value is None:
        return ""
    return f"{value:.2f}"

def get_tax_percent_formatted(rt):
    if rt.taxPercent is None:
        return ""
    return f"{rt.taxPercent:.2f}"
#========= ZREPORT ====================
def create_zreport(fiscalday,invoice_type, currency, daily_total, vatable_net_amount, vatable_tax, nonvatable_net):
    # Adjust values based on invoice type
    if invoice_type == "FISCALINVOICE":
        if nonvatable_net > 0:
            vatable_net_amount = daily_total - nonvatable_net
    else:  # e.g., CREDITNOTE
        if abs(nonvatable_net) > 0:
            vatable_net_amount = -(abs(daily_total) - abs(nonvatable_net))

    # Check for existing record in OpenDay
    existing = frappe.db.get_value(
        "Openday",
        filters={"invoice_type": invoice_type, "currency": currency},fieldname="name"
    )

    if existing:
        # Load and update the record
        doc = frappe.get_doc("Openday", existing)
        doc.daily_total = "{:.2f}".format(float(doc.daily_total) + float(daily_total))
        doc.vatable_net_amount = "{:.2f}".format(float(doc.vatable_net_amount) + float(vatable_net_amount))
        doc.vatable_tax = "{:.2f}".format(float(doc.vatable_tax) + float(vatable_tax))
        doc.nonvatable_net = "{:.2f}".format(float(doc.nonvatable_net) + float(nonvatable_net))
        doc.fiscal_day = fiscalday
        doc.docstatus = 1
        doc.flags.skip_zreport_hooks = True
        doc.save()
    else:
        # Create new record
        doc = frappe.new_doc("Openday")
        doc.invoice_type = invoice_type
        doc.currency = currency
        doc.daily_total = "{:.2f}".format(float(daily_total))
        doc.vatable_net_amount = "{:.2f}".format(float(vatable_net_amount))
        doc.vatable_tax = "{:.2f}".format(float(vatable_tax))
        doc.nonvatable_net = "{:.2f}".format(float(nonvatable_net))
        doc.fiscal_day = fiscalday
        doc.docstatus = 1
        doc.flags.skip_zreport_hooks = True
        doc.insert()

    frappe.db.commit()
#========= PROCESS EOD =============
def process_eod_report(mycounters: list, fiscal_day: int) -> str:
    sb = []

    # Fetch records from Openday Doctype
    records = frappe.get_all("Openday", filters={"fiscal_day": fiscal_day}, fields=[
        "currency", "daily_total", "vatable_net_amount", "vatable_tax",
        "nonvatable_net", "invoice_type"
    ])

    if not records:
        return ""

    # Group by currency
    from collections import defaultdict
    by_currency = defaultdict(list)
    for rec in records:
        by_currency[rec.currency].append(rec)

    currency_order = sorted(by_currency.keys())

    for currency_name in currency_order:
        currency_records = by_currency[currency_name]

        # FISCALINVOICE
        fiscal_records = [r for r in currency_records if r.invoice_type == "FISCALINVOICE"]
        for rec in fiscal_records:
            # Non-VATable
            if float(rec.nonvatable_net or 0) != 0:
                sb.append(f"SALEBYTAX{currency_name}0.00{float(rec.nonvatable_net) * 100:.0f}")
                mycounters.append(FiscalCounter(
                    fiscalCounterCurrency=currency_name,
                    fiscalCounterTaxID=int(get_config_value("tax0")),
                    fiscalCounterType="SALEBYTAX",
                    fiscalCounterTaxPercent=0.00,
                    fiscalCounterMoneyType=None,
                    fiscalCounterValue=float(f"{float(rec.nonvatable_net):.2f}")
                ))
            # VATable
            sb.append(f"SALEBYTAX{currency_name}15.00{float(rec.vatable_net_amount) * 100:.0f}")
            mycounters.append(FiscalCounter(
                fiscalCounterCurrency=currency_name,
                fiscalCounterTaxID=int(get_config_value("tax15")),
                fiscalCounterType="SALEBYTAX",
                fiscalCounterTaxPercent=15.00,
                fiscalCounterMoneyType=None,
                fiscalCounterValue=float(f"{float(rec.vatable_net_amount):.2f}")
            ))
            sb.append(f"SALETAXBYTAX{currency_name}15.00{float(rec.vatable_tax) * 100:.0f}")
            mycounters.append(FiscalCounter(
                fiscalCounterCurrency=currency_name,
                fiscalCounterTaxID=int(get_config_value("tax15")),
                fiscalCounterType="SALETAXBYTAX",
                fiscalCounterTaxPercent=15.00,
                fiscalCounterMoneyType=None,
                fiscalCounterValue=float(f"{float(rec.vatable_tax):.2f}")
            ))

        # CREDITNOTE
        credit_records = [r for r in currency_records if r.invoice_type == "CREDITNOTE"]
        for rec in credit_records:
            if float(rec.nonvatable_net or 0) != 0:
                sb.append(f"CREDITNOTEBYTAX{currency_name}0.00{float(rec.nonvatable_net) * 100:.0f}")
                mycounters.append(FiscalCounter(
                    fiscalCounterCurrency=currency_name,
                    fiscalCounterTaxID=int(get_config_value("tax0")),
                    fiscalCounterType="CREDITNOTEBYTAX",
                    fiscalCounterTaxPercent=0.00,
                    fiscalCounterMoneyType=None,
                    fiscalCounterValue=float(f"{float(rec.nonvatable_net):.2f}")
                ))

            sb.append(f"CREDITNOTEBYTAX{currency_name}15.00{float(rec.vatable_net_amount) * 100:.0f}")
            mycounters.append(FiscalCounter(
                fiscalCounterCurrency=currency_name,
                fiscalCounterTaxID=int(get_config_value("tax15")),
                fiscalCounterType="CREDITNOTEBYTAX",
                fiscalCounterTaxPercent=15.00,
                fiscalCounterMoneyType=None,
                fiscalCounterValue=float(f"{float(rec.vatable_net_amount):.2f}")
            ))

            sb.append(f"CREDITNOTETAXBYTAX{currency_name}15.00{float(rec.vatable_tax) * 100:.0f}")
            mycounters.append(FiscalCounter(
                fiscalCounterCurrency=currency_name,
                fiscalCounterTaxID=int(get_config_value("tax15")),
                fiscalCounterType="CREDITNOTETAXBYTAX",
                fiscalCounterTaxPercent=15.00,
                fiscalCounterMoneyType=None,
                fiscalCounterValue=float(f"{float(rec.vatable_tax):.2f}")
            ))

    # BALANCEBYMONEYTYPE aggregation
    from collections import defaultdict
    currency_totals = defaultdict(float)
    for rec in records:
        currency_totals[rec.currency] += float(rec.daily_total)

    for currency, total in sorted(currency_totals.items()):
        sb.append(f"BALANCEBYMONEYTYPE{currency}CASH{total * 100:.0f}")
        mycounters.append(FiscalCounter(
            fiscalCounterCurrency=currency,
            fiscalCounterTaxID=None,
            fiscalCounterType="BALANCEBYMONEYTYPE",
            fiscalCounterTaxPercent=None,
            fiscalCounterMoneyType="CASH",
            fiscalCounterValue=float(f"{total:.2f}")
        ))

    return "".join(sb)
#========CONVERT DATE ===================
def convert_to_date(input_date: str) -> str:
    date_time = datetime.strptime(input_date, "%Y-%m-%dT%H:%M:%S")
    return date_time.strftime("%Y-%m-%d")
#========= CLOSE FISCAL DAY  REQUEST ===============
def close_fiscal_day():
    result = ""
    try:
        base_url = get_config_value("server_url")
        fiscal_counter_list = []

        # Compose string to hash and sign
        fiscal_date_opened = convert_to_date(get_config_value("fiscal_date"))
        fiscal_counters_data = "{}{}{}{}".format(
            int(get_config_value("device_id")), get_config_value("fiscal_day"),
            fiscal_date_opened,
            process_eod_report(fiscal_counter_list, int(get_config_value("fiscal_day")))
        )

        close_day_hash = Signature.compute_hash(fiscal_counters_data)
        print(fiscal_counters_data)

        close_day_signature = Signature.sign_data(fiscal_counters_data, get_private_key_path())

        # Build fiscal day object
        fiscal_day_obj = FiscalDay(
            deviceID=get_config_value("device_id"),
            fiscalDayNo=int(get_config_value("fiscal_day").strip()),
            fiscalDayCounters=fiscal_counter_list,
            fiscalDayDeviceSignature=FiscalDayDeviceSignature(
                hash=close_day_hash,
                signature=close_day_signature
            ),
            receiptCounter=int(get_config_value("receiptcounter").strip())
        )

        close_day_json_string = json.dumps(fiscal_day_obj.to_dict(), indent=4)
        
        zimra_url = f"{base_url}/Device/v1/{get_config_value('device_id')}/CloseDay"
        print(zimra_url)
        # build SSL context and load your PFX
        ssl_ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        ssl_ctx.load_cert_chain(certfile=get_pem_cert_path(), keyfile=get_private_key_path())

        headers = {
            "accept": "application/json",
            "DeviceModelName": "Server",
            "DeviceModelVersion": "v1",
            "Content-Type": "application/json"
        }

        with httpx.Client(verify=ssl_ctx) as client:
            response =  client.post(zimra_url,data=close_day_json_string,headers=headers)

        # log raw response
        #frappe.log_error(frappe.get_traceback(),"Raw response: %s", response.text)
        
        if response.status_code == 200:
            result = response.text
            json_obj = response.json()
            frappe.log_error(frappe.get_traceback(),"Raw response: " + response.text)
            #update_config_value("FiscalDayStatus", "FiscalDayClosed")
            return result
        else:
            result = response.text
            frappe.log_error(frappe.get_traceback(),"Close day Failed")
            return result

    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Error in CloseFiscalDay")
        result = "Failed"
        return result
#==========CLOSE DAY HOOK ===================
@frappe.whitelist()
def closeday(docname):
    close_fiscal_day()
    time.sleep(30)
    msg = send_private_request(ReqType.Status, "GET")
    return msg
    #frappe.throw("Fiscal Day Status: " + msg)
#========= SEND INVOICE FUCTION ===========
def send_invoice(AddCustomer, InvoiceFlag, Currency, BranchName, InvoiceNumber,
                       CustomerName, TradeName, CustomerVATNumber, CustomerAddress,
                       CustomerTelephoneNumber, CustomerTIN, CustomerProvince,
                       CustomerStreet, CustomerHouseNo, CustomerCity, CustomerEmail,
                       InvoiceAmount, InvoiceTaxAmount, InvoiceComment,
                       OriginalInvoiceNo, GlobalInvoiceNo, ItemsXML):
    
    valid_currencies = ["ZWG", "USD", "EUR", "GBP"]
    receipt_type = ""
    receipt_notes = None
    #is_connected = await is_internet_available()

    if AddCustomer == "0":
        CustomerProvince = None
        CustomerStreet = None
        CustomerHouseNo = None
        CustomerCity = None
        CustomerEmail = ""
        CustomerTelephoneNumber = ""

    if Currency.upper() == "ZIG":
        Currency = "ZWG"

    try:
        ItemsXML = ItemsXML.replace("&", "and")
        xml_root = ET.fromstring(ItemsXML)
    except Exception as ex:
        return json.dumps({
            "Message": f"Invalid ItemXml format Reason: {str(ex)}",
            "Date": datetime.now().isoformat()
        }, indent=4)

    if Currency not in valid_currencies:
        return json.dumps({
            "Message": "Invalid Currency, Only ZWG, USD, EUR and GBP are allowed",
            "Date": datetime.now().isoformat()
        }, indent=4)

    validation_result = validate_xml_structure(xml_root)
    if validation_result:
        return validation_result

    #check_havano_zimra_folder()

    nonvatable = 0
    #receipt_date = datetime.now().isoformat()
    fdate = datetime.now()
    receipt_date = fdate.strftime("%Y-%m-%dT%H:%M:%S")
    qr_date = datetime.now().strftime("%d%m%Y")

    item_list = []
    taxes_item_list = []
    

    lcount = 0
    sales_plus_tax = 0
    tax_amount = 0
    sales_tax = 0

    global_receipt_no = int(get_config_value("receipt_globalno")) + 1
    receipt_counter = int(get_config_value("receiptcounter")) + 1

    buyer_data = None
    if AddCustomer != "0":
        buyer_data = BuyerData(
            buyerRegisterName=CustomerName,
            buyerTradeName=TradeName,
            vatNumber=CustomerVATNumber,
            buyerTIN=CustomerTIN,
            buyerContacts=BuyerContacts(phoneNo=CustomerTelephoneNumber, email=CustomerEmail),
            buyerAddress=BuyerAddress(
                province=CustomerProvince,
                street=CustomerStreet,
                houseNo=CustomerHouseNo,
                city=CustomerCity
            )
        )

    for item_node in xml_root.findall("ITEM"):
        item_code = item_node.find("ITEMCODE").text
        item_name = item_node.find("ITEMNAME").text
        qty = float(item_node.find("QTY").text)
        price = float(item_node.find("PRICE").text)
        tax_per: float = float(item_node.find("VATR").text)
        vat_rate = float(tax_per * 100)
        total = float(item_node.find("TOTAL").text)
        vat = calculate_tax_amount(total, vat_rate)
        vtype = item_node.find("VNAME").text.strip()

        lcount += 1
        sales_plus_tax += total
        if vat != 0:
            tax_amount += vat
            sales_tax += total

        tcode = "A"
        tax_percent = 0.0
        if vtype == "VAT":
            tid = int(get_config_value("tax15"))
            tcode = "C"
            tax_percent = float(15.00)
        elif vtype == "EXEMPT":
            tid = int(get_config_value("taxe"))
        elif vtype == "ZERO RATED":
            tid = int(get_config_value("tax0"))
            tcode = "B"

        if vat == 0:
            nonvatable += total

        add_or_update_tax_item(InvoiceFlag, taxes_item_list, tcode, tax_percent, tid, total, vat, vtype)

        receipt_item = ReceiptLine(
            receiptLineType="Sale",
            receiptLineNo=lcount,
            receiptLineHSCode=item_code,
            receiptLineName=item_name,
            receiptLineQuantity=qty,
            receiptLinePrice=-price if InvoiceFlag == 1 else price,
            taxID=tid,
            taxCode=tcode,
            taxPercent=vat_rate if vtype != "EXEMPT" else None,
            receiptLineTotal=-total if InvoiceFlag == 1 else total
        )
        item_list.append(receipt_item)

    for tax in taxes_item_list:
        tax.taxAmount = round(tax.taxAmount, 2)
        tax.salesAmountWithTax = round(tax.salesAmountWithTax, 2)
    sales_plus_tax = round(sales_plus_tax, 2)
    credit_note = None
    if InvoiceFlag == 1:
        receipt_notes = OriginalInvoiceNo
        receipt_type = "CREDITNOTE"
        credit_note = asdict(CreditDebitNote(
            receiptID=None,
            deviceID=get_config_value("device_id"),
            receiptGlobalNo=int(GlobalInvoiceNo),
            fiscalDayNo=int(get_config_value("fiscal_day"))
        ))
        sales_plus_tax = -sales_plus_tax
    else:
        receipt_type = "FISCALINVOICE"

    prev_receipt_hash = get_config_value("previous_receipt_hash")
    filtered_taxes = sorted(
        [item for item in taxes_item_list if str(item.taxID) in ["1", "2", "3"]],
        key=lambda x: str(x.taxID)
    )
    
    # receipt_taxes_str = "".join(
    #     f"{t.taxCode}{t.taxPercent or '0.00'}{int(t.taxAmount * 100)}{int(t.salesAmountWithTax * 100)}"
    #     for t in filtered_taxes
    # )
    receipt_taxes_str= ""
    
    for rt in filtered_taxes:
        tax_code = rt.taxCode
        tax_percent = get_tax_percent_formatted(rt)
        stax_amount = float(rt.taxAmount) * 100
        stax_amount = round(stax_amount)
        #sales_with_tax = int(rt.salesAmountWithTax * 100)
        sales_with_tax = int(round(rt.salesAmountWithTax * 100))
        receipt_taxes_str += f"{tax_code}{tax_percent}{stax_amount}{sales_with_tax}"
    
    print(receipt_taxes_str)
    # return ""
    concat_receipt_data = Signature.concatenate_data(
        int(get_config_value("device_id")),
        receipt_type,
        Currency,
        str(global_receipt_no),
        receipt_date,
        int(round(sales_plus_tax * 100)),
        receipt_taxes_str,
        prev_receipt_hash
    )
    print(concat_receipt_data)

    receipt_hash = Signature.compute_hash(concat_receipt_data)
    receipt_signature = Signature.sign_data(concat_receipt_data, get_private_key_path())
    qr_code = ReceiptQRCodes.generate_qr_code(
        get_config_value("verify_server"),
        get_config_value("device_id"),
        qr_date,
        str(global_receipt_no),
        receipt_signature
    )
    verification_code = ReceiptQRCodes.generate_verification_code(receipt_signature)

    receipt_obj = receiptWrapper(receipt={
        "receiptType": receipt_type,
        "receiptCurrency": Currency,
        "receiptCounter": receipt_counter,
        "receiptGlobalNo": global_receipt_no,
        "invoiceNo": InvoiceNumber,
        "buyerData": asdict(buyer_data),
        "receiptNotes": receipt_notes,
        "receiptDate": receipt_date,
        "creditDebitNote": credit_note,
        "receiptLinesTaxInclusive": True,
        "receiptLines": [asdict(item) for item in item_list],
        "receiptTaxes": [asdict(tax) for tax in taxes_item_list],
        "receiptPayments": [{"moneyTypeCode": "Cash", "paymentAmount": sales_plus_tax}],
        "receiptTotal": sales_plus_tax,
        "receiptPrintForm": "Receipt48",
        "receiptDeviceSignature": {
            "hash": receipt_hash,
            "signature": receipt_signature
        }
    })

    json_string = json.dumps(receipt_obj.__dict__, indent=4, default=str)
    
    #print(json_string)
    # return ""
    
    edf_serial = get_config_value("device_serial")

    response_data = {
        "Message": "Invoice Successfully Sent to Zimra",
        "QRcode": qr_code,
        "VerificationCode": verification_code,
        "DeviceID": get_config_value("device_id"),
        "FiscalDay": get_config_value("fiscal_day"),
        "receiptType": receipt_type,
        "receiptCurrency": Currency,
        "receiptCounter": receipt_counter,
        "receiptGlobalNo": global_receipt_no,
        "EFDSERIAL": edf_serial
    }
    
    result = ""
    is_connected = True #is_internet_available()

    if is_connected:
        result =  send_to_zimra(json_string, "/SubmitReceipt")
    else:
        #queue_invoice(str(global_receipt_no), str(receipt_counter), InvoiceFlag, Currency, BranchName,
                      #InvoiceNumber, CustomerName, TradeName, CustomerVATNumber, CustomerAddress,
                      #CustomerTelephoneNumber, CustomerTIN, InvoiceAmount, InvoiceTaxAmount,
                      #InvoiceComment, OriginalInvoiceNo, GlobalInvoiceNo, ItemsXML,
                      #AddCustomer, CustomerEmail, CustomerProvince, CustomerStreet,
                      #CustomerHouseNo, CustomerCity)
        result = "Queued"

    if result == "Success":
        update_sales_invoice(InvoiceNumber,global_receipt_no,get_config_value("fiscal_day"),edf_serial,get_config_value("device_id"),qr_code, verification_code)

        update_config_value("previous_receipt_hash", receipt_hash)
        update_config_value("receiptcounter", str(receipt_counter))
        update_config_value("receipt_globalno", str(global_receipt_no))
        
        if InvoiceFlag == 1:
            tax_amount = -tax_amount
            sales_tax = -sales_tax
            nonvatable = -nonvatable
        create_zreport(get_config_value("fiscal_day"),receipt_type, Currency, sales_plus_tax, sales_tax, tax_amount, nonvatable)

    return result

#AddCustomer, InvoiceFlag, Currency, BranchName, InvoiceNumber,
                       #CustomerName, TradeName, CustomerVATNumber, CustomerAddress,
                    #    CustomerTelephoneNumber, CustomerTIN, CustomerProvince,
                    #    CustomerStreet, CustomerHouseNo, CustomerCity, CustomerEmail,
                    #    InvoiceAmount, InvoiceTaxAmount, InvoiceComment,
                    #    OriginalInvoiceNo, GlobalInvoiceNo, ItemsXML
def remove_newlines(text: str) -> str:
    return text.replace("\n", "")

def generate_qr_base64(data: str) -> str:
    """Generate a base64-encoded PNG image from the given data string."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return f"data:image/png;base64,{img_base64}"

def update_sales_invoice(invoice_name: str, receipt_no: str, fiscal_day: str, device_serial: str, device_id: str, qr_code_data: str, verification_code: str):
    try:
        # Load the Sales Invoice
        sales_invoice = frappe.get_doc("Sales Invoice", invoice_name)

        # Generate QR code from string
        qr_base64 = generate_qr_base64(qr_code_data)

        # Update custom fields
        sales_invoice.custom_zimra_status = 1
        sales_invoice.custom_receiptno = receipt_no
        sales_invoice.custom_device_id = device_id
        sales_invoice.custom_fiscal_day = fiscal_day
        sales_invoice.custom_invoice_qr_code = qr_base64  # You can also store just the base64 string
        sales_invoice.custom_verification_code = verification_code
        sales_invoice.custom_device_serial_no = device_serial

        # Save and commit
        sales_invoice.save(ignore_permissions=True)
        frappe.db.commit()
        return True
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to update Sales Invoice")
        frappe.msgprint(f"Error: {e}")
        return False

def generate_random_zimra_item_id(vat: str) -> str:
    try:
        vat_value = float(vat)
        if vat_value > 0:
            random_number = random.randint(99001000, 99001999)
        else:
            random_number = random.randint(99002000, 99002999)
        return str(random_number)
    except ValueError:
        raise ValueError("Invalid VAT input: must be numeric.")    
  
def send(doc, method):
    tradeName= ""
    cus_vat_no= "" 
    cus_address= ""
    cus_no= "" 
    cus_tin= ""
    cus_province= ""
    cus_street= ""
    cus_house_no= ""
    customer_city= "" 
    customer_email= ""
    
    invoice_number=doc.name
    customer = doc.customer
    invoice_amount = doc.grand_total
    posting_date = doc.posting_date
    iscreditnote = doc.is_return
    invoice_currency = doc.currency
    invoice_receiptno = ""
    company = doc.company
    original_invoiceno = doc.return_against

    if iscreditnote:
        invoice_cr = frappe.get_all("Sales Invoice",
    filters={"name": original_invoiceno},fields=["custom_receiptno"]
    )
        for inv in invoice_cr:
            invoice_receiptno = inv.custom_receiptno

    itm_xml = "<ITEMS>"
    cus = frappe.get_all(
    "Customer",
    filters={"customer_name": customer},
    fields=["custom_trade_name", "custom_customer_tin","custom_customer_vat", "custom_customer_address", "custom_telephone_number", "custom_province","custom_street","custom_house_no","custom_city","custom_email_address"]
    )
    for cusinfo in cus:
        trade_name= cusinfo.custom_trade_name
        cus_vat_no= cusinfo.custom_customer_vat 
        cus_address= cusinfo.custom_customer_address
        cus_no= cusinfo.custom_telephone_number 
        cus_tin= cusinfo.custom_customer_tin
        cus_province= cusinfo.custom_province
        cus_street= cusinfo.custom_street
        cus_house_no= cusinfo.custom_house_no
        customer_city= cusinfo.custom_city
        customer_email= cusinfo.custom_email_address

    items = frappe.get_all(
    "Sales Invoice Item",
    filters={"parent": invoice_number},
    fields=["item_code", "item_name", "qty", "rate", "amount"]
    )
    rcount=0
    for item in items:
        item_code = item.item_code
        item_name = item.item_name
        qty = abs(float(item.qty))
        price = abs(float(item.rate))
        total = abs(float(item.amount))
        rcount +=1
        # Get tax info from tabItem Tax (assuming it's linked to Item)
        tax_info = frappe.get_all(
            "Item Tax",
            filters={"parent": item_code},
            fields=["tax_category", "maximum_net_rate"]
        )

        # Default values if tax not found
        tax_category = ""
        max_net_rate = 0.0

        if tax_info:
            tax_category = tax_info[0].tax_category
            max_net_rate = float(tax_info[0].maximum_net_rate or 0)
            max_net_rate = max_net_rate / 100

        # Calculate VAT (tax is inclusive in price)
        #vat = price - (price / (1 + max_net_rate)) if max_net_rate else 0.0
        tax_rate = max_net_rate / 100
        vat = price * tax_rate / (1 + tax_rate)

        # Build XML fragment
        hscode = generate_random_zimra_item_id(vat)
        itm_xml += f"""
        <ITEM>
            <HH>{rcount}</HH>
            <ITEMCODE>{hscode}</ITEMCODE>
            <ITEMNAME>{item_name}</ITEMNAME>
            <QTY>{qty}</QTY>
            <PRICE>{price}</PRICE>
            <TOTAL>{total}</TOTAL>
            <VAT>{round(vat, 2)}</VAT>
            <VATR>{max_net_rate}</VATR>
            <VNAME>{tax_category}</VNAME>
        </ITEM>
        """
    itm_xml += "</ITEMS>"
    itm = remove_newlines(itm_xml)
    #print(itm)
    response_msg =  send_invoice(
        "1", iscreditnote, invoice_currency, company, invoice_number, customer, trade_name,
        cus_vat_no,cus_address,cus_no,cus_tin,cus_province,
         cus_street,cus_house_no, customer_city,customer_email,
        invoice_amount, "0.00", "", original_invoiceno, invoice_receiptno, itm)
    #if response_msg=="Success":
        #frappe.show_alert('Invoice successfully sent to Zimra', 3);
        #frappe.show_alert({message:__('Invoice successfully sent to Zimra')indicator:'green'}, 5);
        
    #frappe.msgprint(f"Response: {response_msg}")
    #frappe.throw(msg)
    
    #return ""

# async def main():
#     itm = "<ITEMS><ITEM><HH>1</HH><ITEMCODE>99001868</ITEMCODE><ITEMNAME>Milo</ITEMNAME><ITEMNAME2>Milo</ITEMNAME2><QTY>1</QTY><PRICE>6.1</PRICE><TOTAL>6.1</TOTAL><VAT>0.8</VAT><VATR>0.15</VATR><VNAME>VAT</VNAME></ITEM><ITEM><HH>2</HH><ITEMCODE>99002638</ITEMCODE><ITEMNAME>Dano Refill</ITEMNAME><ITEMNAME2>Dano Refill</ITEMNAME2><QTY>1</QTY><PRICE>5.1</PRICE><TOTAL>5.1</TOTAL><VAT>0</VAT><VATR>0.00</VATR><VNAME>ZERO RATED</VNAME></ITEM><ITEM><HH>3</HH><ITEMCODE>99002384</ITEMCODE><ITEMNAME>Bournvita</ITEMNAME><ITEMNAME2>Bournvita</ITEMNAME2><QTY>1</QTY><PRICE>5.8</PRICE><TOTAL>5.8</TOTAL><VAT>0</VAT><VATR>0.00</VATR><VNAME>EXEMPT</VNAME></ITEM></ITEMS>"
#     msg = await send_invoice(
#         "0", 0, "USD", "Havano Supermarket", "ERPT1-0013", "Donsol Tester", "Adeola Sat",
#         "220102816", "14, Arundel Road, Alexandra Park, Harare", "081474650", "2001423860",
#         "testProvice", "testStreet", "tA1", "testCity", "donsoltest@gmail.com",
#         "4.60", "0.60", "", "INV-03050001", "", itm)
#     print(msg)
    
# if __name__ == "__main__":
#     asyncio.run(main())
    