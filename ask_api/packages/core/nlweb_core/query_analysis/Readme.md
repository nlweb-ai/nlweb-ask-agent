
This directory contains the code for analysing the user's
query to determine the course of action.

The set of analysis that can be done is extensive and 
specified in the file query_analysis.xml in this directory.

Each query analysis has an entry in this file. An entry
may be enabled or not. 

Query analysis can be of two types:
a) run a prompt and store the structured response as part
    of the query_analysis field of the NLWebHandler
b) run an arbitrary piece of code as specified in the xml.