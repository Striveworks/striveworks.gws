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
            self.module.fail_json(
                msg=f"Error creating user: {email}"
            )  # add to exit message

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
            self.module.fail_json(
                msg=f"Error updating user: {email}"
            )  # add to exit message


def main():

    argument_spec = {
        "auth_email": {"type": "str", "required": True},
        "auth_scopes": {"type": "list", "required": True},
        "auth_dictionary": {"type": "dict", "required": True},
        "users": {"type": "list", "required": True},
    }

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    gws = AnsibleGWS(module)

    users = module.params["users"]
    # module.fail_json(msg=f"Users: {users}")
    for ansible_user in users:
        try:
            email = ansible_user["email"]
            given_name = ansible_user["givenname"]
            surname = ansible_user["surname"]
            suspended = ansible_user["suspended"]
            is_admin = ansible_user["gws_admin"]
        except Exception as e:
            module.fail_json(msg=f"User: {email} is missing required fields.\n{e}")

        if email == "" or "@" not in email:
            module.fail_json(
                msg=f"Need valid email. Given: {email}"
            )  # add to exit message

        user = gws.get_user(email)

        if user is None:
            password = (
                ansible_user["password"]
                if ansible_user.get("password")
                else gws.get_random_password()
            )
            if module.check_mode:
                gws.exit_messages.append(f"User {email} would be created")
            else:
                user = gws.create_user(
                    email, given_name, surname, is_admin, suspended, password, is_admin
                )

        elif user["suspended"] != suspended or user["isAdmin"] != is_admin:
            if module.check_mode:
                gws.exit_messages.append(
                    f"User {email} would be updated with suspended: {suspended} and is_admin: {is_admin}"
                )
            else:
                user = gws.update_user(email, suspended, is_admin)

    module.params["auth_dictionary"] = "REDACTED"
    module.params["users"] = "REDACTED"
    module.exit_json(changed=bool(gws.exit_messages), msg="\n".join(gws.exit_messages))


if __name__ == "__main__":
    main()
