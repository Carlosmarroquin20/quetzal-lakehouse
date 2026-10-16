# Values for the local AWS emulator; see docs/aws.md. The emulator serves
# plain HTTP, which the TLS-only bucket policy would refuse, and is reached
# through a hostname that needs path-style addresses.
name_prefix       = "quetzal-emulator"
require_tls       = false
s3_use_path_style = true
