#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {
    'status': ['preview'],
    'supported_by': 'community',
    'metadata_version': '0.1'
}

DOCUMENTATION = '''
---
module: s3_tag
short_description: create and remove tags on S3 buckets.
description:
    - Creates, removes and lists tags for any S3 bucket.  The bucket is referenced by its name.
      It is designed to be used with complex args (tags), see the examples.
    - This module was based of 'ec2_tag' module
version_added: "2.7"
requirements: [ "boto3", "botocore" ]
options:
  bucket:
    description:
      - Name of S3 bucket.
    required: true
  state:
    description:
      - Whether the tags should be present or absent on the S3 bucket. Use list to interrogate the tags of a bucket.
    default: present
    choices: ['present', 'absent', 'list']
  tags:
    description:
      - a hash/dictionary of tags to add to the S3 bucket; '{"key":"value"}' and '{"key":"value","key":"value"}'
      - in case of 'state=absent' it uses "key" do determine which tags to remove. "value" part must be present, but it is ignored.
    required: true
  purge_tags:
    description:
      - Whether to ignore currently applied tags(set tags from scratch).
    type: bool
    default: yes
    version_added: '2.7'

author:
  - Marko Celan (@markocelan)
extends_documentation_fragment:
    - aws
'''

EXAMPLES = '''
- name: Ensure 'owner' and 'env' tags are present on a S3 bucket
  s3_tag:
    bucket: test-bucket-123456
    state: present
    tags:
      owner: Jon Snow
      env: prod

- name: Ensure _only_ 'owner' and 'env' tags are present on a S3 bucket
  s3_tag:
    bucket: test-bucket-123456
    state: present
    purge_tags: yes
    tags:
      owner: Jon Snow
      env: prod

- name: Delete single tag
  s3_tag:
    region:  eu-west-1
    bucket: test-bucket-123456
    state: absent
    tags:
      owner: 'this value is ignored'

- name: Retrieve all tags of a bucket
  s3_tag:
    bucket: test-bucket-123456
    state: list
  register: s3_tags

- name: Remove all tags from a bucket
  s3_tag:
    bucket: test-bucket-123456
    tags: {}
    state: present
    purge_tags: yes
'''

RETURN = '''
tags:
  description: A dict containing the tags on the S3 bucket
  returned: always
  type: dict
wanted_tags:
  description: A dict of tags that should belong to the S3 bucket. Usually indicates something failure applying tags without throwing an exception. This shouldn't happen.
  returned: when wanted_tags and tags differ.
  type: dict
'''

from ansible.module_utils.aws.core import AnsibleAWSModule
from ansible.module_utils.ec2 import boto3_tag_list_to_ansible_dict, ansible_dict_to_boto3_tag_list, compare_aws_tags

try:
    from botocore.exceptions import BotoCoreError, ClientError
except:
    pass  # Handled by AnsibleAWSModule


def get_tags(s3, module, bucket):
    try:
        tags = s3.get_bucket_tagging(Bucket=bucket).get('TagSet')
        return boto3_tag_list_to_ansible_dict(tags)
    except (BotoCoreError, ClientError) as e:
        if e.operation_name == 'GetBucketTagging':
            return None
        module.fail_json_aws(
            e, msg='Failed to fetch tags for bucket {0}'.format(bucket))


def main():
    argument_spec = dict(
        bucket=dict(required=True),
        tags=dict(type='dict'),
        purge_tags=dict(type='bool', default=True),
        state=dict(default='present', choices=['present', 'absent', 'list']),
    )
    required_if = [('state', 'present', ['tags']), ('state', 'absent',
                                                    ['tags'])]

    module = AnsibleAWSModule(
        argument_spec=argument_spec,
        required_if=required_if,
        supports_check_mode=True)

    bucket = module.params['bucket']
    tags = module.params['tags']
    state = module.params['state']
    purge_tags = module.params['purge_tags']

    result = {'changed': False}

    s3 = module.client('s3')

    current_tags = get_tags(s3, module, bucket)

    if state == 'list':
        module.exit_json(changed=False, tags=current_tags)

    wanted_tags = {}
    if state == 'absent':
        for key, val in current_tags.items():
            if key not in tags:
                wanted_tags[key] = val

    elif state == 'present':
        if purge_tags:
            # forget about previously applied tags
            wanted_tags = tags.copy()
        else:
            # append/update previously applied tags
            if current_tags:
                wanted_tags = current_tags.copy()
            else:
                wanted_tags = dict()
            wanted_tags.update(tags)

    if current_tags != wanted_tags:
        result['changed'] = True
        try:
            if len(wanted_tags) < 1:
                s3.delete_bucket_tagging(Bucket=bucket)
                wanted_tags = None
            else:
                s3.put_bucket_tagging(
                    Bucket=bucket,
                    Tagging={
                        'TagSet': ansible_dict_to_boto3_tag_list(wanted_tags)
                    })
        except (BotoCoreError, ClientError) as e:
            module.fail_json_aws(
                e,
                msg='Failed to update tags {0} from bucket {1}'.format(
                    wanted_tags, bucket))

    if module.check_mode:
        result['tags'] = wanted_tags
    else:
        result['tags'] = get_tags(s3, module, bucket)

    if wanted_tags != result['tags']:  # maybe throw an error here?
        result['wanted_tags'] = wanted_tags

    module.exit_json(**result)


if __name__ == '__main__':
    main()
