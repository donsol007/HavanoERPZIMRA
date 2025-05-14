import frappe
from frappe import _, msgprint, throw

def startday(doc, method):
    fd = frappe.db.get_single_value("Zimra Account", "fiscal_day") #frappe.get_single("Zimra Account")
    default_currency = frappe.db.get_single_value("System Settings", "currency")  #settings = frappe.get_single("System Settings")
   
    doc.fiscal_day = int(fd) + 1
    doc.currency = default_currency