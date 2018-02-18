bank-statements
===============

Usage: `python3 bank.py [-s]`.

Script to parse bank statements downloaded from Natwest, HSBC and Santander and
print an aggregated statement in CSV format to standard output.

Alternatively, use `-s` flag to group transactions by week and print a
spending report.

Statement output is in the form
```
Date,nw-statement-1.csv,nw-statement-2.csv,...,santander-statement.txt,total
DD-MM-YYYY,<balance>,<balance>,...,<balance>,<total balance>
...
```

Statements are looked for at `statements/natwest/*.csv`, `statements/hsbc/*.csv`
and `statements/santander/*.txt`.

Natwest statements should be downloaded by going to `Statements` ->
`Download or export transactions`. For `Time period`, choose `Last 4 months`,
and for `Download/export type` choose `Excel, Lotus 123, Text (CSV file)`.

Santander statements should be downloaded by going to `View transactions` ->
`Download transactions`. Choose `Text file (TXT)` format in the `Download to`
dropdown.

Tests can by run with `pytest test.py`.
