"""
excel.py - Excel Database Logger Module for Bus Monitoring System
------------------------------------------------------------------
This module manages the automated record keeping using OpenPyXL and Pandas.
It logs bus entry and exit timestamps, calculates campus duration,
and prevents duplicate log entries in 'bus_gate_log.xlsx'.
"""

import os
import threading
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
import pandas as pd


class ExcelLogger:
    """
    ExcelLogger creates and updates Excel spreadsheets to track campus bus activity.
    """
    
    def __init__(self, filename: str = "bus_gate_log.xlsx"):
        """
        Initialize the Excel Logger.

        :param filename: Target Excel spreadsheet path
        """
        self.filename = filename
        self.columns = [
            "Log ID", "Vehicle ID", "Registration Plate", "Direction",
            "Entry Time", "Exit Time", "Duration (Minutes)", "Date", "Status"
        ]
        self._lock = threading.Lock()  # Prevents concurrent write corruption
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create styled Excel file with column headers if it does not exist."""
        if not os.path.exists(self.filename):
            print(f"[INFO] Creating new Excel database log: {self.filename}")
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Gate Activity Logs"
            
            # Write Header Row
            ws.append(self.columns)
            
            # Apply Header Formatting (Navy Blue Fill with Bold White Text)
            header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            align_center = Alignment(horizontal="center", vertical="center")
            
            for col_num in range(1, len(self.columns) + 1):
                cell = ws.cell(row=1, column=col_num)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = align_center

            # Set Column Widths
            widths = [10, 15, 22, 14, 20, 20, 20, 15, 15]
            for i, col_letter in enumerate(["A", "B", "C", "D", "E", "F", "G", "H", "I"]):
                ws.column_dimensions[col_letter].width = widths[i]

            wb.save(self.filename)

    def log_vehicle(self, vehicle_id: int, plate_no: str, direction: str) -> dict:
        """
        Log an entry or exit event to the Excel file.
        Updates an existing 'ON CAMPUS' record if exiting, or creates a new entry record.
        Thread-safe via internal lock.

        :param vehicle_id: Unique tracked vehicle ID number
        :param plate_no: Recognized bus plate number string (e.g., 'TN38AB1234')
        :param direction: 'Entry' or 'Exit'
        :return: Recorded log dictionary summary
        """
        now = datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        plate_clean = plate_no.upper() if plate_no else "UNKNOWN"

        with self._lock:
            wb = openpyxl.load_workbook(self.filename)
            ws = wb["Gate Activity Logs"]

            # Check if plate is already currently inside campus without an exit timestamp
            updated_existing = False
            if direction == "Exit":
                for row_idx in range(2, ws.max_row + 1):
                    row_plate = ws.cell(row=row_idx, column=3).value
                    row_status = ws.cell(row=row_idx, column=9).value

                    if row_plate == plate_clean and row_status == "ON CAMPUS":
                        entry_time_str = ws.cell(row=row_idx, column=5).value
                        try:
                            entry_dt = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
                            duration_mins = round((now - entry_dt).total_seconds() / 60.0, 1)
                        except Exception:
                            duration_mins = 0.0

                        ws.cell(row=row_idx, column=6, value=timestamp_str)  # Exit Time
                        ws.cell(row=row_idx, column=7, value=duration_mins)   # Duration
                        ws.cell(row=row_idx, column=9, value="EXITED")         # Status
                        updated_existing = True
                        break

            if not updated_existing:
                # Auto-increment log ID: data rows start at row 2, so ID = max_row (header is row 1)
                log_id = ws.max_row  # After append this becomes max_row+1; gives unique sequential IDs
                status = "ON CAMPUS" if direction == "Entry" else "EXITED"
                entry_t = timestamp_str if direction == "Entry" else "-"
                exit_t = timestamp_str if direction == "Exit" else "-"
                duration = "-"

                new_row = [log_id, f"BUS-{vehicle_id}", plate_clean, direction,
                           entry_t, exit_t, duration, date_str, status]
                ws.append(new_row)

                # Apply cell styling
                align = Alignment(horizontal="center", vertical="center")
                for c in range(1, len(new_row) + 1):
                    ws.cell(row=ws.max_row, column=c).alignment = align

            wb.save(self.filename)

        print(f"[EXCEL LOG] Logged {direction} for Bus {plate_clean} at {timestamp_str}")

        return {
            "vehicle_id": vehicle_id,
            "plate": plate_clean,
            "direction": direction,
            "timestamp": timestamp_str
        }

    def get_logs_dataframe(self) -> pd.DataFrame:
        """Read current logs from Excel file into a pandas DataFrame."""
        if not os.path.exists(self.filename):
            return pd.DataFrame(columns=self.columns)
            
        try:
            df = pd.read_excel(self.filename, sheet_name="Gate Activity Logs")
            return df
        except Exception as e:
            print(f"[ERROR] Reading Excel file failed: {e}")
            return pd.DataFrame(columns=self.columns)

    def get_summary_stats(self) -> dict:
        """Calculate and return key performance indicators (KPIs)."""
        df = self.get_logs_dataframe()
        if df.empty or "Status" not in df.columns:
            return {
                "total_records": 0,
                "on_campus": 0,
                "exited_today": 0,
                "model_status": "Active (YOLOv8 + EasyOCR)"
            }
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        total_records = len(df)
        on_campus = len(df[df["Status"] == "ON CAMPUS"])
        exited_today = len(df[(df["Status"] == "EXITED") & (df["Date"].astype(str) == today_str)])
        
        return {
            "total_records": total_records,
            "on_campus": on_campus,
            "exited_today": exited_today,
            "model_status": "Active (YOLOv8 + EasyOCR)"
        }

    def get_records_list(self, search_query: str = "", status_filter: str = "ALL") -> list:
        """Return list of dict log records with optional filtering."""
        df = self.get_logs_dataframe()
        if df.empty:
            return []
        
        # Ensure strings for search comparison
        df = df.fillna("-")
        
        if search_query:
            q = search_query.strip().lower()
            df = df[
                df["Registration Plate"].astype(str).str.lower().str.contains(q) |
                df["Vehicle ID"].astype(str).str.lower().str.contains(q) |
                df["Direction"].astype(str).str.lower().str.contains(q)
            ]
            
        if status_filter and status_filter != "ALL":
            df = df[df["Status"].astype(str).str.upper() == status_filter.upper()]
            
        return df.to_dict(orient="records")



# --- Simple Module Test ---
if __name__ == "__main__":
    print("[TEST] Initializing ExcelLogger test...")
    logger = ExcelLogger("test_bus_log.xlsx")
    
    # Test logging Entry
    logger.log_vehicle(vehicle_id=1, plate_no="TN38CB2026", direction="Entry")
    
    # Test logging Exit
    logger.log_vehicle(vehicle_id=1, plate_no="TN38CB2026", direction="Exit")
    
    df = logger.get_logs_dataframe()
    print("[TEST] Current Excel Log Data:")
    print(df)
