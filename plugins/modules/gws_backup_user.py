# elif state == "deleted":
#     if user is not None:
#         archived =  gws.user_check_backup(email)
#         if archived:
#             gws.delete_user(email)
#         else:
#             # archive user or fail
#             module.fail_json(msg=f"User: {email} not archived")
import io
import os
import json
from ansible.module_utils.basic import AnsibleModule
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
import time
from google.cloud import storage
import googleapiclient.http
import zipfile


DOCUMENTATION = """
---
module: gws_backup_user
short_description: Backup Google Workspace user
description: Delete google workspace user
author: "Will Albers (@walbers)"
"""


class AnsibleGWS:
    def __init__(self, module):
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            module.params["auth_dictionary"], scopes=module.params["auth_scopes"]
        )
        credentials = credentials.create_delegated(module.params["auth_email"])
        self.transfer_client = build(
            "admin", "datatransfer_v1", credentials=credentials
        )
        self.directory_client = build("admin", "directory_v1", credentials=credentials)
        self.vault_client = build("vault", "v1", credentials=credentials)
        self.storage_client_download = build("storage", "v1", credentials=credentials)
        self.storage_client_upload = storage.Client.from_service_account_json(
            module.params["storage_creds_path"]
        )
        self.module = module
        self.exit_messages = []

    def get_user(self, email):
        try:
            user = self.directory_client.users().get(userKey=email).execute()
            return user
        except Exception as e:
            self.module.fail_json(msg=f"Failed to get user: {email}\n{e}")

    def transfer_data(self, user, receiver):
        try:
            resp = (
                self.transfer_client.transfers()
                .insert(
                    body={
                        "oldOwnerUserId": user,
                        "newOwnerUserId": receiver,
                        "applicationDataTransfers": [
                            {
                                "applicationId": "55656082996",
                                "applicationTransferParams": [
                                    {
                                        "key": "PRIVACY_LEVEL",
                                        "value": ["PRIVATE", "SHARED"],
                                    }
                                ],
                            }
                        ],
                    }
                )
                .execute()
            )
            self.exit_messages.append(f"Transferred data from {user} to {receiver}")
        except Exception as e:
            self.module.fail_json(
                msg=f"Failed to transfer data from {user} to {receiver}\n{e}"
            )

    def create_matter(self, user, matter_owner):
        try:
            matter_name = user.split("@")[0] + " export matter"
            self.exit_messages.append(f"Creating matter named {matter_name}")
            matter = (
                self.vault_client.matters()
                .create(
                    body={
                        "name": matter_name,
                        "state": "OPEN",
                        "matterPermissions": [
                            {"accountId": matter_owner, "role": "OWNER"}
                        ],
                    }
                )
                .execute()
            )
            self.exit_messages.append(f"Created matter for {user}")
            return matter
        except Exception as e:
            self.module.fail_json(msg=f"Failed to create matter for {user}\n{e}")

    def create_mail_export(self, user, matter_id, bucket_name):
        try:
            matter_name = user.split("@")[0] + " export matter"
            export = (
                self.vault_client.matters()
                .exports()
                .create(
                    matterId=matter_id,
                    body={
                        "name": matter_name,
                        "query": {
                            "corpus": "MAIL",
                            "dataScope": "ALL_DATA",
                            "method": "ACCOUNT",
                            "accountInfo": {"emails": [user]},
                            "mailOptions": {"excludeDrafts": False},
                        },
                        "exportOptions": {
                            "mailOptions": {
                                "exportFormat": "MBOX",
                                "showConfidentialModeContent": True,
                                "useNewExport": True,
                            }
                        },
                    },
                )
                .execute()
            )
            self.exit_messages.append(f"Created mail export for {user}")
            return export
        except Exception as e:
            self.module.fail_json(msg=f"Failed to create export for {user}\n{e}")

    def download_file(self, path, bucket_name, object_name):
        req = self.storage_client_download.objects().get_media(
            bucket=bucket_name, object=object_name
        )
        file_name = path + object_name.split("/")[-1]
        try:
            with io.FileIO(file_name, mode="wb") as out_file:
                downloader = googleapiclient.http.MediaIoBaseDownload(out_file, req)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    time.sleep(5)
            self.exit_messages.append(f"Downloaded file: {object_name} to {file_name}")
        except Exception as e:
            self.module.fail_json(msg=f"Failed to download file: {object_name}\n{e}")

    def zip_files(self, path, user):
        files_and_directories = os.listdir(path)
        files = [
            f for f in files_and_directories if os.path.isfile(os.path.join(path, f))
        ]
        with zipfile.ZipFile(f"{path}{user}.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_name in files:
                temp = zipf.write(os.path.join(path, file_name), file_name)
        self.exit_messages.append(f"Zipped files in {path} to {path}{user}.zip")

    def upload_zip(self, path, user, bucket_name):
        try:
            self.storage_client_upload.bucket(bucket_name).blob(
                f"{user}.zip"
            ).upload_from_filename(f"{path}{user}.zip")
            self.exit_messages.append(f"Uploaded {user}.zip to {bucket_name}")
        except Exception as e:
            self.module.fail_json(
                msg=f"Failed to upload {user}.zip to {bucket_name}\n{e}"
            )

    def delete_files(self, path):
        files_and_directories = os.listdir(path)
        files = [
            f for f in files_and_directories if os.path.isfile(os.path.join(path, f))
        ]
        for file_name in files:
            os.remove(os.path.join(path, file_name))
        self.exit_messages.append(f"Deleted files in {path}")


def main():

    argument_spec = {
        "auth_email": {"type": "str", "required": True},
        "auth_scopes": {"type": "list", "required": True},
        "auth_dictionary": {"type": "dict", "required": True},
        "user": {"type": "str", "required": True},
        "receiver": {"type": "str", "required": True},
        "matter_owner": {"type": "str", "required": True},
        "bucket_name": {"type": "str", "required": True},
        "download_path": {"type": "str", "required": True},
        "storage_creds_path": {"type": "str", "required": True},
    }

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    gws = AnsibleGWS(module)

    user = module.params["user"]
    receiver = module.params["receiver"]
    matter_owner = module.params["matter_owner"]
    bucket_name = module.params["bucket_name"]
    path = module.params["download_path"]

    user_details = gws.get_user(user)
    receiver_details = gws.get_user(receiver)

    # Transfer drive data
    if user_details["suspended"] is False and receiver_details["suspended"] is False:
        gws.transfer_data(user_details["id"], receiver_details["id"])
    else:
        module.fail_json(msg=f"User, {user}, or receiver, {receiver}, is suspended")

    # Backup emails to GCS
    # Matter is a container for exports. Exports exist within a matter
    matter_owner_details = gws.get_user(matter_owner)
    matter = gws.create_matter(user, matter_owner_details["id"])
    export = gws.create_mail_export(user, matter["matterId"], bucket_name)
    sleep = 0
    while export["status"] != "COMPLETED":
        time.sleep(10)
        sleep += 10
        if sleep > 600:
            module.fail_json(
                msg=f"Export took longer than 10 minutes to create. Timing out."
            )
        export = (
            gws.vault_client.matters()
            .exports()
            .get(matterId=export["matterId"], exportId=export["id"])
            .execute()
        )

    # Download, zip up export files, upload to bucket, clean up files
    for export_file in export["cloudStorageSink"]["files"]:
        gws.download_file(path, export_file["bucketName"], export_file["objectName"])
    gws.zip_files(path, user.split("@")[0])
    gws.upload_zip(path, user.split("@")[0], bucket_name)
    gws.delete_files(path)

    # Add check mode

    module.params["auth_dictionary"] = "REDACTED"
    module.exit_json(changed=bool(gws.exit_messages), msg="\n".join(gws.exit_messages))


if __name__ == "__main__":
    main()
