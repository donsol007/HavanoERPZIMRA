from dataclasses import dataclass, field
from typing import Optional, List, Any

@dataclass
class BuyerContacts:
    phoneNo: str
    email: str

@dataclass
class BuyerAddress:
    province: str
    street: str
    houseNo: str
    city: str

@dataclass
class BuyerData:
    buyerRegisterName: str
    buyerTradeName: str
    vatNumber: str
    buyerTIN: str
    buyerContacts: BuyerContacts
    buyerAddress: BuyerAddress

@dataclass
class CreditDebitNote:
    receiptID: Any
    deviceID: str
    receiptGlobalNo: int
    fiscalDayNo: int

@dataclass
class ReceiptLine:
    receiptLineType: str
    receiptLineNo: int
    receiptLineHSCode: str
    receiptLineName: str
    receiptLinePrice: float
    receiptLineQuantity: float
    receiptLineTotal: float
    taxCode: str
    taxPercent: Optional[float]
    taxID: int

@dataclass
class ReceiptTax:
    taxCode: str
    taxPercent: Optional[float]
    taxID: int
    taxAmount: float
    salesAmountWithTax: float

@dataclass
class ReceiptPayment:
    moneyTypeCode: str
    paymentAmount: float

@dataclass
class ReceiptDeviceSignature:
    hash: str
    signature: str

@dataclass
class Receipt:
    receiptType: str
    receiptCurrency: str
    receiptCounter: int
    receiptGlobalNo: int
    invoiceNo: str
    buyerData: BuyerData
    receiptNotes: str
    receiptDate: str
    creditDebitNote: CreditDebitNote
    receiptLinesTaxInclusive: bool
    receiptLines: List[ReceiptLine]
    receiptTaxes: List[ReceiptTax]
    receiptPayments: List[ReceiptPayment]
    receiptTotal: float
    receiptPrintForm: str
    receiptDeviceSignature: ReceiptDeviceSignature

@dataclass
class receiptWrapper:
    receipt: Receipt
