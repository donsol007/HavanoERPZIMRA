from dataclasses import dataclass, asdict
from typing import Optional, List

@dataclass
class FiscalCounter:
    fiscalCounterType: Optional[str] = None
    fiscalCounterCurrency: Optional[str] = None
    fiscalCounterTaxPercent: Optional[float] = None
    fiscalCounterTaxID: Optional[int] = None
    fiscalCounterMoneyType: Optional[str] = None
    fiscalCounterValue: float = 0.0

@dataclass
class FiscalDayDeviceSignature:
    hash: Optional[str] = None
    signature: Optional[str] = None

@dataclass
class FiscalDay:
    deviceID: Optional[str] = None
    fiscalDayNo: int = 0
    fiscalDayCounters: List[FiscalCounter] = None
    fiscalDayDeviceSignature: Optional[FiscalDayDeviceSignature] = None
    receiptCounter: int = 0
   
    def to_dict(self):
            return {
                "deviceID": self.deviceID,
                "fiscalDayNo": self.fiscalDayNo,
                "fiscalDayCounters": [asdict(fc) for fc in self.fiscalDayCounters] if self.fiscalDayCounters else [],
                "fiscalDayDeviceSignature": asdict(self.fiscalDayDeviceSignature) if self.fiscalDayDeviceSignature else None,
                "receiptCounter": self.receiptCounter
            }
