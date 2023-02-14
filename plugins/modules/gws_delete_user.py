# user - creating, disabling                - done
# groups - creating, modifiying             - done

# archive/delete - users                    - doing


# drives - creating, modifiying, deleting
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

    def delete_user(self, email):
        try:
            self.client.users().delete(userKey=email).execute()
            self.exit_messages.append(f"Deleted user {email}")
        except Exception as e:
            self.module.fail_json(msg=f"Failed to delete user {email}", error=e)

    def remove_hold(self, hold_name):
        try:
            self.client.holds().delete(holdId=hold_name).execute()
            self.exit_messages.append(f"Removed hold {hold_name}")
        except Exception as e:
            self.module.fail_json(msg=f"Failed to remove hold {hold_name}", error=e)

    def add_hold(self, hold_name):
        try:
            self.client.holds().insert(body={"name": hold_name}).execute()
            self.exit_messages.append(f"Added hold {hold_name}")
        except Exception as e:
            self.module.fail_json(msg=f"Failed to add hold {hold_name}", error=e)


def main():

    argument_spec = {
        "auth_email": {"type": "str", "required": True},
        "auth_scopes": {"type": "list", "required": True},
        "auth_dictionary": {"type": "dict", "required": True},
        "email": {"type": "str", "required": True},
        "hold_name": {"type": "str", "required": False},
        "require_backup": {"type": "bool", "required": False, "default": False},
        "backup_name": {"type": "str", "required": False},
    }

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    gws = AnsibleGWS(module)

    email = module.params["email"]
    hold_name = module.params.get("hold_name")
    require_backup = module.params["require_backup"]
    backup_name = module.params.get("backup_name")

    if email == "" or "@" not in email:
        module.fail_json(msg=f"Need valid email. Given: {email}")

    user = gws.get_user(email)

    if user:
        if user["suspended"]:
            if require_backup:
                backup = gws.is_backed_up(backup_name)
                if not backup:
                    module.fail_json(msg=f"User {email} is not backed up.")

            if hold_name:
                gws.remove_hold(hold_name)
                gws.delete_user(email)
                gws.add_hold(hold_name)
            else:
                gws.delete_user(email)
        else:
            module.fail_json(msg=f"User {email} is not suspended.")

    module.params["auth_dictionary"] = "REDACTED"
    module.exit_json(changed=bool(gws.exit_messages), msg="\n".join(gws.exit_messages))


if __name__ == "__main__":
    main()
