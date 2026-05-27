# Notlob

Notlob is an experiment in literate programming for human and machine agents. 


## Idea

The basic visible structures are source files that colocate and interleave all the executable and natural language elements related to a particular concept. The key underlying data structure is a queryable name-graph that connects conceptual structure, such as titles and nouns, with executable elements such as functions and tests.

This is intended to be a codebase explaining itself to itself. Design artifacts can be tied closely to executables, and consistency demonstrated with every build. 

Holding related concepts together with their examples and checkable formal properties can have two specific benefits for LLM coding agents. A single source file economises on context window and extra tool calls. Searches in the codebase can be done via the name-graph tooling, rather than requiring auxiliary filesystem searches that increase token costs and information loss through handoffs. When an LLM agent reads a notlob source file, the most important materials are already laid oout on the workbench, ready to go.

## Bindings

Notlob currently uses well established language toolsets for the executable elements. Two bindings are provided, for Python and Haskell. A binding kit includes language, unit tests, and property tests.


## Example





## Installing and Developing 

Notlob is written in Python. Create a venv, clone and build using pip in the usual way.



## Running Notlob

Two basic commands, each with subcommands and help. `notlob` is for build time. `lob` is for runtime.




## Origin and Ideas

Notlob is inspired by the insights of Knuth, Peter Naur, Dominic Fox, and Name Oriented Programming.

Notlob was written at arms length using Claude. This README is completely hand authored. Every other artifact, including DESIGN.md, has been emitted or altered by the language extrusion machine as the result of dialogue.

Notlob is not Python, and is not a palindrome.


