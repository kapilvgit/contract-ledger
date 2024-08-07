# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import argparse
import json
import re
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .. import crypto, did


class RegistrationInfoType(Enum):
    TEXT = "text"
    BYTES = "bytes"
    INT = "int"


class RegistrationInfoArgument:
    type: RegistrationInfoType
    name: str
    content: str

    # This won't support names that contain an '=' or ':'.
    # This is probably fine for the time being, but we should have a scheme to escape those.
    PATTERN = re.compile("((?P<type>[^=:]+):)?" "(?P<name>[^=:]+)=" "(?P<content>.*)")

    def __init__(self, value: str):
        match = self.PATTERN.fullmatch(value)
        if not match:
            raise argparse.ArgumentTypeError(
                f"'{value}' is not a valid registration info argument"
            )

        type_ = match.group("type")
        if type_ is None:
            self.type = RegistrationInfoType.TEXT
        else:
            try:
                self.type = RegistrationInfoType(type_)
            except Exception as e:
                raise argparse.ArgumentTypeError(
                    f"'{type}' is not a valid registration info type"
                ) from None

        self.name = match.group("name")
        self.content = match.group("content")

    def value(self) -> crypto.RegistrationInfoValue:
        if self.content.startswith("@"):
            data = Path(self.content[1:]).read_bytes()
        else:
            data = self.content.encode("ascii")

        if self.type is RegistrationInfoType.INT:
            return int(data.decode("utf-8"))
        elif self.type is RegistrationInfoType.TEXT:
            return data.decode("utf-8")
        elif self.type is RegistrationInfoType.BYTES:
            return data


def create_signer_from_arguments(
    key_path: Path,
    did_doc_path: Optional[Path],
    kid: Optional[str],
    issuer: Optional[str],
    algorithm: Optional[str],
) -> crypto.Signer:
    key = crypto.load_private_key(key_path)

    if did_doc_path is not None:
        if issuer or algorithm:
            raise ValueError(
                "The --issuer and --alg flags may not be used together with a DID document."
            )

        with open(did_doc_path) as f:
            did_doc = json.load(f)
        return did.get_signer(key, did_doc, kid)

    else:
        return crypto.Signer(key, issuer, kid, algorithm)


def sign_contract(
    contract_path: Path,
    key_path: Path,
    out_path: Path,
    did_doc_path: Optional[Path],
    issuer: Optional[str],
    content_type: str,
    algorithm: Optional[str],
    kid: Optional[str],
    participant_info: List[str],
    feed: Optional[str],
    add_signature: bool,
):
    signer = create_signer_from_arguments(
        key_path, did_doc_path, kid, issuer, algorithm
    )
    contract = contract_path.read_bytes()

    signed_contract = crypto.sign_contract(
        signer,
        contract,
        content_type,
        add_signature,
        feed,
        participant_info,
    )

    print(f"Writing {out_path}")
    out_path.write_bytes(signed_contract)


def cli(fn):
    parser = fn(description="Sign a contract")
    parser.add_argument(
        "--contract", type=Path, required=True, help="Path to contract file"
    )
    parser.add_argument(
        "--key", type=Path, required=True, help="Path to PEM-encoded private key"
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for signed claimset (must end in .cose)",
    )

    # Signing with an existing DID document
    parser.add_argument("--did-doc", type=Path, help="Path to DID document")

    # Ad-hoc signing, without any on-disk document
    parser.add_argument("--issuer", help="Issuer stored in envelope header")
    parser.add_argument("--alg", help="Signing algorithm to use.")

    parser.add_argument(
        "--content-type", required=True, help="Content type of contract"
    )
    parser.add_argument("--kid", help='Key ID ("kid" field) to use if multiple')
    parser.add_argument("--feed", help='Optional "feed" stored in envelope header')
    parser.add_argument(
        "--participant-info",
        metavar="NAME",
        action="append",
        type=str,
        default=[],
        help="""
        Pariticpant information to be stored in the envelope header.
        The flag may be specified multiple times, once per partipant entry.
        If content has the form `@file.txt`, the data will be read from the specified file instead.
        """,
    )

    parser.add_argument(
        "--add-signature",
        help="Add signature to existing contract",
        action="store_true",
    )

    parser.set_defaults(
        func=lambda args: sign_contract(
            args.contract,
            args.key,
            args.out,
            args.did_doc,
            args.issuer,
            args.content_type,
            args.alg,
            args.kid,
            args.participant_info,
            args.feed,
            args.add_signature,
        )
    )

    return parser


if __name__ == "__main__":
    parser = cli(argparse.ArgumentParser)
    args = parser.parse_args()
    args.func(args)
