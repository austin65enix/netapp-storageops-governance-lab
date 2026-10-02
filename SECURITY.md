# Security

This repository is a synthetic infrastructure and governance lab.

It must not contain:

- production ONTAP credentials
- customer or corporate storage inventories
- private keys or authentication tokens
- production IP addresses or hostnames
- real serial numbers
- raw production incident logs
- confidential operational evidence

All example storage objects and identities should be synthetic.

If credentials are required for local testing, use environment variables or
a local `.env` file. `.env` is excluded from version control.

Historical runtime evidence from the original development environment is not
included in the public repository.
