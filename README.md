bank-statements
===============

Script to parse bank statements downloaded from Natwest (.csv format) and
Santander (.txt format) and print an aggregated statement in CSV format to
standard output.

Output is in the form
```
Date,nw-statement-1.csv,nw-statement-2.csv,...,santander-statement.txt,total
DD-MM-YYYY,<balance>,<balance>,...,<balance>,<total balance>
...
```

Statements are looked for in `statements/natwest` and `statements/santander`.
