# Himotoki Data Directory

This directory should contain the following data files:

## JMDict XML

- `JMdict_e.xml` - The JMDict dictionary XML file
  - Download from: http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz
  - Ungzip and place in this directory

## JMdictDB Conjugation Data

The following CSV files come from the JMdictDB project:

- `kwpos.csv` - Part of speech definitions
- `conj.csv` - Conjugation type descriptions  
- `conjo.csv` - Conjugation rules

These can be found in the JMdictDB project:
https://gitlab.com/yamagoya/jmdictdb/-/tree/master/jmdictdb/data

Download these files and place them in this directory.

## Sample Data Structure

### kwpos.csv (tab-separated)
```
id	kw	descr
1	n	noun
2	pn	pronoun
...
46	v1	Ichidan verb
47	v1-s	Ichidan verb - kureru special class
...
```

### conj.csv (tab-separated)
```
id	descr
1	Non-past
2	Past (~ta)
3	Conjunctive (~te)
...
```

### conjo.csv (tab-separated)
```
pos	conj	neg	fml	onum	stem	okuri	euphr	euphk	pos2
46	1	f	f	1	1	る	
46	1	t	f	1	1	ない	
...