# AGENTS.md

Check README.md for overall project context and setup instructions.

## Writing tool plugins for agentkit:

- If there is an error, do not raise an exception, instead return a string with the error message. This will be sent to the LLM and can be used to correct the input