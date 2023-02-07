import json
from ansible.module_utils.basic import AnsibleModule
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials

DOCUMENTATION = """
---
module: gws_groups
short_description: Manage Google Workspace groups
description: Manage Google Workspace groups
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

    def get_all_groups(self):
        try:
            groups = self.client.groups().list().execute()
        except Exception as e:
            groups = None
        return groups

    def get_group(self, email):
        try:
            group = self.client.groups().get(groupKey=email).execute()
        except Exception as e:
            group = None
        return group

    def get_group_members(self, email):
        try:
            members = self.client.members().list(groupKey=email).execute()
        except Exception as e:
            self.module.fail_json(msg=f"Failed to get members for group: {email}")
        return members

    def create_group(self, name, email, description=None):
        try:
            self.client.groups().insert(
                body={
                    "name": name,
                    "email": email,
                    "description": description,
                }
            ).execute()

            self.exit_messages.append(f"Created group: {name}")
        except Exception as e:
            self.fail_json(msg=f"Failed to create group: {name}")

    def create_group_member(self, group_email, member_email, role):
        try:
            self.client.members().insert(
                groupKey=group_email, body={"email": member_email, "role": role}
            ).execute()
            self.exit_messages.append(
                f"Added user: {member_email} to group: {group_email} with role: {role}"
            )
        except Exception as e:
            self.module.fail_json(
                msg=f"Failed to add member: {member_email} to group: {group_email} with role: {role}\n{e}"
            )

    def update_group_member(self, group_email, member_email, role):
        try:
            self.client.members().patch(
                groupKey=group_email, memberKey=member_email, body={"role": role}
            ).execute()
            self.exit_messages.append(
                f"Updated user: {member_email} in group: {group_email} to role: {role}"
            )
        except Exception as e:
            self.module.fail_json(
                msg=f"Failed to update user: {member_email} in group: {group_email} to role: {role}\n{e}"
            )

    def delete_group_member(self, group_email, member_email):
        try:
            self.client.members().delete(groupKey=group_email, memberKey=member_email)
            self.exit_messages.append(
                f"Deleted user: {member_email} from group: {group_email}"
            )
        except Exception as e:
            self.module.fail_json(
                msg=f"Failed to delete user: {member_email} from group: {group_email}\n{e}"
            )


def main():

    argument_spec = {
        "auth_email": {"type": "str", "required": True},
        "auth_scopes": {"type": "list", "required": True},
        "auth_dictionary": {"type": "dict", "required": True},
        "groups": {"type": "list", "required": True},
        # "email": {"type": "str", "required": True},
        # "name": {"type": "str", "required": False},
        # "description": {"type": "str", "required": False},
        # "members": {
        #     "type": "list",
        #     "required": False,
        # },  # list of dictionaries of emails and roles
    }

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    gws = AnsibleGWS(module)

    # can use get all groups

    groups = module.params["groups"]

    for group in groups:
        try:
            email = group["email"]
            name = group["name"]
            description = group["description"]
            members = group["members"]
        except KeyError as e:
            module.fail_json(msg=f"Group {email} is missing required key: {e}")

        gws_group = gws.get_group(email)
        if gws_group is None:
            if self.module.check_mode:
                gws.exit_messages.append(f"Would have created group: {name}")
            else:
                gws.create_group(name, email, description)
                group_members = []
        else:
            group_members = gws.get_group_members(email).get("members")
            if group_members is None:
                group_members = {}
            else:
                group_members = {
                    member["email"]: member["role"] for member in group_members
                }

        member_email_set = set()
        if members is not None:
            for member in members:
                if "@" not in member["email"]:
                    module.fail_json(
                        msg=f"Need valid email for member. Given: {member['email']}"
                    )
                elif member["role"] not in ["MEMBER", "MANAGER", "OWNER"]:
                    module.fail_json(
                        msg=f"Need valid role for member. Given: {member['role']}"
                    )
                elif member["email"] not in group_members:
                    if module.check_mode:
                        gws.exit_messages.append(
                            f"Would have added user: {member['email']} to group: {email} with role: {member['role']}"
                        )
                    else:
                        gws.create_group_member(email, member["email"], member["role"])
                elif group_members[member["email"]] != member["role"]:
                    if module.check_mode:
                        gws.exit_messages.append(
                            f"Would have updated user: {member['email']} in group: {email} to role: {member['role']}"
                        )
                    else:
                        gws.update_group_member(email, member["email"], member["role"])
                member_email_set.add(member["email"])

        need_to_remove = set(group_members.keys()) - member_email_set
        if need_to_remove:
            for member in need_to_remove:
                if module.check_mode:
                    gws.exit_messages.append(
                        f"Would have removed: {member} from group: {email}"
                    )
                else:
                    gws.delete_group_member(email, member)

    module.params["auth_dictionary"] = "REDACTED"
    module.exit_json(changed=bool(gws.exit_messages), msg="\n".join(gws.exit_messages))


if __name__ == "__main__":
    main()
