# AGENTS.md

Check README.md for overall project context and setup instructions.

## Writing tool plugins for mikoshi:

- If there is an error, do not raise an exception, instead return a string with the error message. This will be sent to the LLM and can be used to correct the input
- There's no need for backwards compatibility, this is the only live deployment
- If something needs a workaround or hack around mikoshi's current limitations say so. Update to mikoshi's code is preferrable to workarounds.

## Secrets

- domains are considered private and should not be shared publicly