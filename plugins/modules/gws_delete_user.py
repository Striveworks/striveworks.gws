# elif state == "deleted":
#     if user is not None:
#         archived =  gws.user_check_backup(email)
#         if archived:
#             gws.delete_user(email)
#         else:
#             # archive user or fail
#             module.fail_json(msg=f"User: {email} not archived")
