"""CSV for spreadsheets (review 08.11. H2-7): a text cell that starts with = + - @ Tab or CR is read by Excel/LibreOffice
as a formula („+2 Mace“ becomes #NAME?, a prepared name could do more). Such cells get a ' in front – what every
spreadsheet shows as plain text. Numbers stay numbers.

    w = csvsafe.writer(f, delimiter=";")     # instead of csv.writer – same writerow/writerows
"""
import csv

LEADS = ("=", "+", "-", "@", "\t", "\r")


def cell(v):
    return "'" + v if isinstance(v, str) and v.startswith(LEADS) else v


class writer:
    def __init__(self, f, *args, **kwargs):
        self._w = csv.writer(f, *args, **kwargs)

    def writerow(self, row):
        return self._w.writerow([cell(v) for v in row])

    def writerows(self, rows):
        for r in rows:
            self.writerow(r)
