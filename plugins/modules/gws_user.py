# user - creating, disabling                - done

# groups - creating, modifiying             - doing

# drives - creating, modifiying, deleting
# archive/delete - user, drives,
# need send email task in role


# prepend exit messages to failure message
# add error e to failure message
# check for users/teams that dont exist match with what passed

import json
import random
import string
from ansible.module_utils.basic import AnsibleModule
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials

DOCUMENTATION = """
---
module: gws_user
short_description: Manage Google Workspace users
description: Manage Google Workspace users
author: "Will Albers (@walbers)"
"""


class AnsibleGWS:
    def __init__(self, module):
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            module.params["auth_dictionary"], scopes=module.params["auth_scopes"]
        )
        credentials = credentials.create_delegated(module.params["auth_email"])
        self.client = build("admin", "directory_v1", credentials=credentials)
        self.module = module
        self.exit_messages = []

    def get_user(self, email):
        try:
            user = self.client.users().get(userKey=email).execute()
        except Exception as e:
            user = None
        return user

    def get_random_password(self):
        randchar = string.ascii_letters + string.digits + string.punctuation
        return "".join(random.choice(randchar) for i in range(12))

    def create_user(
        self, email, given_name, surname, role, suspended, password, is_admin
    ):
        try:
            user = (
                self.client.users()
                .insert(
                    body={
                        "primaryEmail": email,
                        "password": password,
                        "isAdmin": is_admin,
                        "suspended": suspended,
                        "name": {"givenName": given_name, "familyName": surname},
                        "changePasswordAtNextLogin": True,
                    }
                )
                .execute()
            )
            self.exit_messages.append(
                f"Created user: {email} with suspended: {suspended} and is_admin: {is_admin}"
            )
            return user
        except Exception as e:
            self.module.fail_json(msg=f"Error creating user: {email}")

    def update_user(self, email, suspended, is_admin):
        try:
            user = (
                self.client.users()
                .update(
                    userKey=email,
                    body={"suspended": suspended, "isAdmin": is_admin},
                )
                .execute()
            )
            self.exit_messages.append(
                f"Updated user: {email} with suspended: {suspended} and is_admin: {is_admin}"
            )
            return user
        except Exception as e:
            self.module.fail_json(msg=f"Error updating user: {email}")


def main():

    argument_spec = {
        "auth_email": {"type": "str", "required": True},
        "auth_scopes": {"type": "list", "required": True},
        "auth_dictionary": {"type": "dict", "required": True},
        "email": {"type": "str", "required": True},
        "password": {"type": "str", "default": ""},
        "given_name": {"type": "str", "required": True},
        "surname": {"type": "str", "required": True},
        "is_admin": {"type": "bool", "default": False},
        "suspended": {"type": "bool", "default": False},
    }

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    gws = AnsibleGWS(module)

    email = module.params["email"]
    given_name = module.params["given_name"]
    surname = module.params["surname"]
    suspended = module.params["suspended"]
    is_admin = module.params["is_admin"]

    if email == "" or "@" not in email:
        module.fail_json(msg=f"Need valid email. Given: {email}")

    user = gws.get_user(email)

    if user is None:
        password = (
            module.params["password"]
            if module.params["password"]
            else gws.get_random_password()
        )
        if module.check_mode:
            module.exit_json(changed=True, msg=f"User {email} would be created")
        else:
            user = gws.create_user(
                email, given_name, surname, is_admin, suspended, password, is_admin
            )

    elif user["suspended"] != suspended or user["isAdmin"] != is_admin:
        if module.check_mode:
            module.exit_json(
                changed=True,
                msg=f"User {email} would be updated with suspended: {suspended} and is_admin: {is_admin}",
            )
        else:
            user = gws.update_user(email, suspended, is_admin)

    module.params["auth_dictionary"] = "REDACTED"
    module.exit_json(changed=bool(gws.exit_messages), msg="\n".join(gws.exit_messages))


if __name__ == "__main__":
    main()
