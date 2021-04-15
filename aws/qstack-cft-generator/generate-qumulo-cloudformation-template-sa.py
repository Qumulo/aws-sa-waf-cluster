#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2018 Qumulo
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# qumulo_python_versions = { 3 }
# mypy: ignore-errors

"""
The purpose of this script is to generate a AWS CloudFormation Template for Qumulo that
is pre-configured for a requested number of cluster nodes, and contains the proper
configuration to allow those cluster nodes to form a cluster and serve clients.

Writes the CFT to stdout.

Qumulo Solution Architect Version (SA)
- Adds Placement Group
- Parameterizes Floating IP in the generated JSON (ignores floating IP input for python input parameter)
- Adds Tags for Nodes
- Formats Instance IDs as simple comma delimited list
- Adds Security Group ID Output

"""

import argparse
import json
import os
import sys

os.environ['TROPO_REAL_BOOL'] = 'true'

from troposphere import (
    AWSAttribute,
    Base64,
    cloudwatch,
    ec2,
    Equals,
    GetAtt,
    If,
    Join,
    Not,
    Output,
    Parameter,
    Ref,
    Sub,
    Tags,
    Template,
)


# NOTE: Use only public packages.

SECURITY_GROUP_NAME = 'QumuloSecurityGroup'
SECURITY_GROUP_DEFAULT_CIDR = '0.0.0.0/0'
KNOWLEDGE_BASE_LINK = 'https://qf2.co/cloud-kb'
CLUSTER_NAME_PATTERN = r'^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$'
CIDR_PATTERN = (
    r'^('
    '([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}'  # (0-255).(0-255).(0-255).
    '([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])'  # (0-255)
    '(\/(3[0-2]|[1-2][0-9]|[0-9])'  # /(0-32)
    ')$'
)
GIBIBYTE = 1024 ** 3


class ChassisSpec:
    def __init__(
        self, volume_count, pairing_ratio, working_spec, backing_spec,
    ):

        assert volume_count <= 25, 'Too many volumes specified'

        self.volume_count = volume_count
        self.pairing_ratio = pairing_ratio
        self.working_spec = working_spec
        self.backing_spec = backing_spec

        self.working_volume_count = self.volume_count / (self.pairing_ratio + 1)
        self.backing_volume_count = self.working_volume_count * self.pairing_ratio
        assert (
            self.volume_count == self.working_volume_count + self.backing_volume_count
        ), 'Not all volumes can be used based on the pairing ratio'
        assert (
            self.backing_volume_count == 0 or self.backing_spec is not None
        ), 'Backing volumes require type and size'

        if self.backing_spec is not None:
            self.backing_volume_size = self.backing_spec['VolumeSize']
            self.backing_device = ec2.EBSBlockDevice(
                **self.backing_spec,
                Encrypted=True,
                KmsKeyId=If(
                    'HasEncryptionKey', Ref('VolumesEncryptionKey'), Ref('AWS::NoValue')
                ),
            )

        self.working_volume_size = self.working_spec['VolumeSize']
        self.working_device = ec2.EBSBlockDevice(
            **self.working_spec,
            Encrypted=True,
            KmsKeyId=If(
                'HasEncryptionKey', Ref('VolumesEncryptionKey'), Ref('AWS::NoValue')
            ),
        )

    @staticmethod
    def from_json(json_spec):
        # Backing disks will not be specified in AF configurations
        return ChassisSpec(
            json_spec.get('slot_count'),
            json_spec.get('pairing_ratio'),
            json_spec.get('working_spec'),
            json_spec.get('backing_spec'),
        )

    def _device_name_from_slot_index(self, slot_index):
        letter = chr(ord('b') + slot_index)
        return '/dev/xvd{}'.format(letter)

    def get_block_device_mappings(self):
        """Create a troposphere mapping for each device"""
        mappings = [
            ec2.BlockDeviceMapping(
                DeviceName='/dev/sda1',
                Ebs=ec2.EBSBlockDevice(
                    Encrypted=True,
                    KmsKeyId=If(
                        'HasEncryptionKey',
                        Ref('VolumesEncryptionKey'),
                        Ref('AWS::NoValue'),
                    ),
                ),
            )
        ]
        for i in range(0, self.volume_count):
            device_name = self._device_name_from_slot_index(i)

            if i < self.working_volume_count:
                device = self.working_device
            else:
                device = self.backing_device

            mappings.append(ec2.BlockDeviceMapping(DeviceName=device_name, Ebs=device))

        return mappings

    def get_slot_specs(self):
        """Create a slot spec json object for each device"""
        slots = []
        for i in range(0, self.volume_count):
            device_name = self._device_name_from_slot_index(i)

            if i < self.working_volume_count:
                disk_role = 'working'
                disk_size = self.working_volume_size * GIBIBYTE
            else:
                disk_role = 'backing'
                disk_size = self.backing_volume_size * GIBIBYTE

            slots.append(
                {
                    'drive_bay': device_name,
                    'disk_role': disk_role,
                    'disk_size': disk_size,
                }
            )

        return {'slot_specs': slots}


class Interface(AWSAttribute):
    dictname = 'AWS::CloudFormation::Interface'

    props = {
        'ParameterGroups': ([dict], True),
        'ParameterLabels': (dict, True),
    }


def add_conditions(template):
    """
    Add HasEncryptionKey, HasIamInstanceProfile, and HasInstanceRecoveryTopic conditions to the template.
    """
    template.add_condition(
        'HasEncryptionKey', Not(Equals(Ref('VolumesEncryptionKey'), ''))
    )
    template.add_condition(
        'HasIamInstanceProfile', Not(Equals(Ref('IamInstanceProfile'), ''))
    )
    template.add_condition(
        'HasInstanceRecoveryTopic', Not(Equals(Ref('InstanceRecoveryTopic'), ''))
    )


def add_params(template, add_ingress_cidr_param):
    """
    Takes a given Template object and adds parameters for user configuration
    """
    """
    Added by SA.  Need the AMI ID entered as a parameter since we can only get one AMI ID
    at a time from the sizer.
    """
    cluster_ami = Parameter(
        'ClusterAMI',
        Description='Qumulo cluster AWS AMI ID',
        Type='String',
    )
    template.add_parameter(cluster_ami)

    cluster_name = Parameter(
        'ClusterName',
        Description='Qumulo cluster name (2-15 alpha-numeric characters and -)',
        Type='String',
        MinLength=2,
        MaxLength=15,
        AllowedPattern=CLUSTER_NAME_PATTERN,
        ConstraintDescription='Name must be an alpha-numeric string between 2 and 15'
        ' characters. Dash (-) is allowed if not the first or last character.',
    )
    template.add_parameter(cluster_name)

    key_name = Parameter(
        'KeyName',
        Description='Name of an existing EC2 KeyPair to enable SSH '
        'access to the node',
        Type='AWS::EC2::KeyPair::KeyName',
    )
    template.add_parameter(key_name)

    instance_type = Parameter(
        'InstanceType',
        Description='EC2 instance type for Qumulo node',
        Type='String',
        Default='m5.4xlarge',
        AllowedValues=[
            'm5.xlarge',
            'm5.2xlarge',
            'm5.4xlarge',
            'm5.8xlarge',
            'm5.12xlarge',
            'm5.16xlarge',
            'm5.24xlarge',
            'c5n.xlarge',
            'c5n.2xlarge',
            'c5n.4xlarge',
            'c5n.9xlarge',
            'c5n.18xlarge',
        ],
        ConstraintDescription='Must be a Qumulo supported EC2 instance type.',
    )
    template.add_parameter(instance_type)

    vpc_id = Parameter(
        'VpcId',
        Description='ID of the VPC in which to deploy Qumulo.',
        Type='AWS::EC2::VPC::Id',
        ConstraintDescription='Must be the ID of an existing VPC.',
    )
    template.add_parameter(vpc_id)

    subnet_id = Parameter(
        'SubnetId',
        Description='ID of the Subnet in which to deploy Qumulo.',
        Type='AWS::EC2::Subnet::Id',
        ConstraintDescription='Must be the ID of an existing Subnet.',
    )
    template.add_parameter(subnet_id)

    sg_cidr = None
    if add_ingress_cidr_param:
        sg_cidr = Parameter(
            'SgCidr',
            Description=(
                'An IPv4 CIDR block for specifying the generated security '
                "group's allowed addresses for inbound traffic. "
                'Set to x.x.x.x/32 to allow one specific IP address '
                'access, 0.0.0.0/0 to allow all IP addresses access, or another '
                'CIDR range.'
            ),
            Type='String',
            AllowedPattern=CIDR_PATTERN,
            ConstraintDescription='Must be specified as an IPv4 address followed '
            'by / and a subnet mask of 0-32.',
        )
        template.add_parameter(sg_cidr)

    volumes_encryption_key = Parameter(
        'VolumesEncryptionKey',
        Type='String',
        Default='',
        Description=(
            'The KMS Key to encrypt the volumes. Use either a key ID, ARN, or '
            'an Alias. Aliases must begin with alias/ followed by the name, '
            'such as alias/exampleKey. If empty, the default KMS EBS key will '
            'be used. Choosing an invalid key name will cause the instance to '
            'fail to launch.'
        ),
    )
    template.add_parameter(volumes_encryption_key)

    iam_instance_profile = Parameter(
        'IamInstanceProfile',
        Type='String',
        Default='',
        Description=(
            'Optionally enter the name (*not* the ARN) of the IAM instance profile to '
            'be assigned to each instance in the cluster.'
        ),
    )
    template.add_parameter(iam_instance_profile)

    instance_recovery_topic = Parameter(
        'InstanceRecoveryTopic',
        Type='String',
        Default='',
        Description=(
            'Optionally enter the ARN of an SNS topic that receives messages when an '
            'instance alarm is triggered.'
        ),
    )
    template.add_parameter(instance_recovery_topic)

    """
    Added by SA
    """
    floating_ip_count = Parameter(
        'FloatingIPCount',
        Type='String',
        Default='0',
        AllowedValues=[
            '0',
            '1',
            '2',
            '3',
            '4',
            '5',
            '6',
            '7',
            '8',
            '9',
            '10',
        ],
        Description=(
            'Optionally enter the number of EC2 Secondary IPs to configure '
            'for use as Floating IPs on the Qumulo Cluster.'
        ),
    )
    template.add_parameter(floating_ip_count)

    parameter_groups = [
        {
            'Label': {'default': 'Amazon EC2 Configuration'},
            'Parameters': [
                cluster_ami.title,
                instance_type.title,
                key_name.title,
                floating_ip_count.title,
                volumes_encryption_key.title,
                iam_instance_profile.title,
            ],
        },
        {
            'Label': {'default': 'Qumulo Configuration'},
            'Parameters': [cluster_name.title,],
        },
        {
            'Label': {'default': 'SNS Configuration'},
            'Parameters': [instance_recovery_topic.title,],
        },
    ]
    parameter_labels = {
        cluster_ami.title: {'default': "Qumulo AMI ID"},
        instance_type.title: {'default': 'EC2 instance type'},
        key_name.title: {'default': 'SSH key-pair name'},
        vpc_id.title: {'default': 'VPC ID'},
        subnet_id.title: {'default': 'Subnet ID in the VPC'},
        cluster_name.title: {'default': 'Qumulo cluster name'},
        volumes_encryption_key.title: {'default': 'EBS volumes encryption key ID'},
        instance_recovery_topic.title: {'default': 'Instance recovery alarm SNS topic'},
        iam_instance_profile.title: {'default': 'IAM Instance Profile'},
        floating_ip_count.title: {'default': 'EC2 Secondary IPs'},
    }
    if sg_cidr:
        parameter_groups.append(
            {
                'Label': {'default': 'Network Configuration'},
                'Parameters': [vpc_id.title, subnet_id.title, sg_cidr.title],
            }
        )
        parameter_labels[sg_cidr.title] = {'default': 'Security group IPv4 CIDR block'}

    template.set_metadata(
        Interface(ParameterGroups=parameter_groups, ParameterLabels=parameter_labels,)
    )

"""
Modified by SA, Region map is useless outside of marketplace
because we can only get an AMI ID for a given disk config for a 
given region from Motle's sizing tool.  Leaving here but commented out.
   

def add_ami_map(template):
    
    Takes a given Template object and AMI ID then creates the Region
    to AMI ID map which is referenced by the add_nodes function.

    template.add_mapping(
        'RegionMap',
        {
            'us-east-1': {'AMI': ami_id},
            'us-east-2': {'AMI': ami_id},
            'us-west-1': {'AMI': ami_id},
            'us-west-2': {'AMI': ami_id},
            'ca-central-1': {'AMI': ami_id},
            'eu-central-1': {'AMI': ami_id},
            'eu-west-1': {'AMI': ami_id},
            'eu-west-2': {'AMI': ami_id},
            'eu-west-3': {'AMI': ami_id},
        },
    )
"""

def add_security_group(template):
    """
    Takes a given Template object and adds properly configured AWS security group to
    enable Qumulo to cluster, replicate, and serve clients.

    Ports enabled by default:
    TCP 21, 22, 80, 111, 443, 445, 2049, 3712, 8000
    UDP 111, 2049

    All traffic is allowed between members of the security group for clustering.
    """

    sg_in = []
    sg_out = []

    # Ingress TCP ports
    tcp_ports = [
        (21, 'FTP'),
        (22, 'SSH'),
        (80, 'HTTP'),
        (111, 'SUNRPC'),
        (443, 'HTTPS'),
        (445, 'SMB'),
        (2049, 'NFS'),
        (3712, 'Replication'),
        (8000, 'REST'),
    ]
    for port, protocol in tcp_ports:
        sg_in.append(
            ec2.SecurityGroupRule(
                Description='TCP ports for {}'.format(protocol),
                IpProtocol='tcp',
                FromPort=port,
                ToPort=port,
                CidrIp=Ref('SgCidr'),
            )
        )

    # Ingress UDP ports
    udp_ports = [(111, 'SUNRPC'), (2049, 'NFS')]
    for port, protocol in udp_ports:
        sg_in.append(
            ec2.SecurityGroupRule(
                Description='UDP port for {}'.format(protocol),
                IpProtocol='udp',
                FromPort=port,
                ToPort=port,
                CidrIp=Ref('SgCidr'),
            )
        )

    # Egress rule for all ports and protocols
    sg_out.append(
        ec2.SecurityGroupRule(
            Description='Outbound traffic',
            IpProtocol='-1',
            FromPort=0,
            ToPort=0,
            CidrIp=SECURITY_GROUP_DEFAULT_CIDR,
        )
    )

    template.add_resource(
        ec2.SecurityGroup(
            SECURITY_GROUP_NAME,
            GroupDescription='Enable ports for NFS/SMB/FTP/SSH, Management, '
            'Replication, and Clustering.',
            SecurityGroupIngress=sg_in,
            SecurityGroupEgress=sg_out,
            VpcId=Ref('VpcId'),
        )
    )

    # Self referencing security rules need to be added after the group is
    # created.  This rule is enabling all traffic between members of the
    # security group for clustering.
    template.add_resource(
        ec2.SecurityGroupIngress(
            'QumuloSecurityGroupNodeRule',
            Description='Qumulo Internode Communication',
            GroupId=Ref(SECURITY_GROUP_NAME),
            IpProtocol='-1',
            FromPort=0,
            ToPort=0,
            SourceSecurityGroupId=Ref(SECURITY_GROUP_NAME),
        )
    )

    return Ref(SECURITY_GROUP_NAME)


def format_slot_specs(slot_specs_json):
    return json.dumps(slot_specs_json, indent=4).split('\n')


def generate_node1_user_data(
    instances, chassis_spec, get_ip_ref=None, cluster_name_ref=None
):

    if get_ip_ref is None:
        get_ip_ref = lambda instance_name: GetAtt(instance_name, 'PrivateIp')

    if cluster_name_ref is None:
        cluster_name_ref = Ref('ClusterName')

    user_data = ['{', '"spec_info": ']
    user_data += format_slot_specs(chassis_spec.get_slot_specs())
    user_data[-1] += ','

    user_data_node_ips = ['"node_ips": [']

    for i, instance in enumerate(instances[1:]):
        if i != 0:
            user_data_node_ips += ', '
        ip = get_ip_ref(instance.title)
        user_data_node_ips += ['"', ip, '"']

    user_data_node_ips += '],'

    user_data += user_data_node_ips

    user_data += ['"cluster_name": "', cluster_name_ref, '" }']

    return user_data


def generate_other_nodes_user_data(chassis_spec):
    user_data = [
        '{',
        '"spec_info": ',
    ]

    user_data += format_slot_specs(chassis_spec.get_slot_specs())
    user_data.append('}')

    return user_data


def add_nodes(
    template, num_nodes, prefix, chassis_spec, security_group
):
    """
    Takes a given Template object, an count of nodes to create, and a name to
    prefix all EC2 instances with.

    EC2 instances will be created with the naming structure of:
        Prefix + 'Node' + NodeNumber
    Network interfaces will be created with the naming structure of
        Prefix + 'Eni' + NodeNumber:
    """
    instances = []
    instance_ids = []
    enis = []

    iam_instance_profile = If(
        'HasIamInstanceProfile', Ref('IamInstanceProfile'), Ref('AWS::NoValue'),
    )

    """
    Added by SA for placement group
    """
    cluster_group = ec2.PlacementGroup(
        'QClusterGroup',
        Strategy='cluster')
    template.add_resource(cluster_group)

    """
    Modified by SA, ImageID now just references the parameter and 2nd IPs the floating IP count
    """
    block_device_mappings = chassis_spec.get_block_device_mappings()
    for node_number in range(1, num_nodes + 1):
        eni = ec2.NetworkInterface(
            '{}Eni{}'.format(prefix, node_number),
            GroupSet=[security_group],
            SubnetId=Ref('SubnetId'),
            SecondaryPrivateIpAddressCount=Ref('FloatingIPCount'),
        )
        template.add_resource(eni)

        eni_prop = ec2.NetworkInterfaceProperty(
            DeviceIndex='0', NetworkInterfaceId=Ref(eni.title),
        )
        
        instance = ec2.Instance(
            '{}Node{}'.format(prefix, node_number),
            ImageId=Ref('ClusterAMI'),
            InstanceType=Ref('InstanceType'),
            KeyName=Ref('KeyName'),
            NetworkInterfaces=[eni_prop],
            BlockDeviceMappings=block_device_mappings,
            EbsOptimized=True,
            IamInstanceProfile=iam_instance_profile,
            PlacementGroupName=Ref('QClusterGroup'),
            Tags=Tags(
                Name=Join(' - ', [Ref('AWS::StackName'), '{}Node{}'.format(prefix, node_number)])),
        )

        enis.append(eni)
        instances.append(instance)
        instance_ids.append(Ref(instance.title))

    instances[0].UserData = Base64(
        Join('', generate_node1_user_data(instances, chassis_spec))
    )

    for instance in instances[1:]:
        instance.UserData = Base64(
            Join('', generate_other_nodes_user_data(chassis_spec))
        )

    for instance in instances:
        template.add_resource(instance)

    instance_recovery_topic = If(
        'HasInstanceRecoveryTopic', Ref('InstanceRecoveryTopic'), Ref('AWS::NoValue'),
    )

    for i, instance in enumerate(instances):
        template.add_resource(
            cloudwatch.Alarm(
                'CWRecoveryAlarm{}'.format(instance.name),
                AlarmActions=[
                    Sub('arn:aws:automate:${AWS::Region}:ec2:recover'),
                    instance_recovery_topic,
                ],
                AlarmDescription=Sub(
                    'Automatic recovery alarm for ${{ClusterName}}-{}'.format(i + 1)
                ),
                ComparisonOperator='GreaterThanOrEqualToThreshold',
                DatapointsToAlarm=2,
                Dimensions=[
                    cloudwatch.MetricDimension(Name='InstanceId', Value=Ref(instance))
                ],
                EvaluationPeriods=2,
                MetricName='StatusCheckFailed_System',
                Namespace='AWS/EC2',
                OKActions=[instance_recovery_topic],
                Period=60,
                Statistic='Maximum',
                Threshold=1.0,
            )
        )

    # Create lists containing the Primary and Secondary Private IPs of all nodes.
    output_primary_ips = []
    output_secondary_ips = []
    for instance, eni in zip(instances, enis):
        output_primary_ips.append(GetAtt(instance.title, 'PrivateIp'))
        secondary_ips = GetAtt(eni.title, 'SecondaryPrivateIpAddresses')
        output_secondary_ips.append(json_format_string(secondary_ips))

    template.add_output(
        Output(
            'ClusterInstanceIDs',
            Description='List of the instance IDs of the nodes in your Qumulo Cluster',
            Value=json_format_string(instance_ids),
        )
    )
    template.add_output(
        Output(
            'ClusterPrivateIPs',
            Description='List of the primary private IPs of the nodes in your Qumulo Cluster',
            Value=json_format_string(output_primary_ips),
        )
    )
    template.add_output(
        Output(
            'ClusterSecondaryPrivateIPs',
            Description='List of the secondary private IPs of the nodes in your Qumulo Cluster',
            Value=json_format_string(output_secondary_ips),
        )
    )
    template.add_output(
        Output(
            'ClusterSGID',
            Description='The security group being used by the cluster network interfaces',
            Value=security_group,
        )
    )
    template.add_output(
        Output(
            'ClusterPlacementGroup',
            Description='The placement group created for the cluster',
            Value=Ref('QClusterGroup'),
        )
    )
    template.add_output(
        Output(
            'TemporaryPassword',
            Description='Temporary admin password for your Qumulo cluster '
            '(exclude quotes, matches node1 instance ID).',
            Value=json_format_quotes(instance_ids[0]),
        )
    )
    template.add_output(
        Output(
            'LinkToManagement',
            Description='Use to launch the Qumulo Admin Console',
            Value=Join('', ['https://', GetAtt(instances[0].title, 'PrivateIp')]),
        )
    )
    template.add_output(
        Output(
            'QumuloKnowledgeBase',
            Description='Knowledge Base for Qumulo in public clouds',
            Value=KNOWLEDGE_BASE_LINK,
        )
    )
    template.add_output(
        Output(
            'AWSStackID',
            Description='AWS ARN for this stack',
            Value=Ref('AWS::StackId'),
        )
    )
    template.add_output(
        Output(
            'AWSStackName',
            Description='AWS Name for this stack',
            Value=Ref('AWS::StackName'),
        )
    )

def json_format_string(s):
    return Join(', ', s)

def json_format_quotes(s):
    return Join('', ['"', s, '"'])

def json_format_list(l):
    return Join('', ['[', Join(', ', l), ']'])


def json_format_list_of_strings(l):
    return Join('', ['["', Join('", "', l), '"]'])


def create_qumulo_cft(
    num_nodes,
    node_name_prefix,
    chassis_spec,
    security_group=None,
):
    """
    This function will return a completed Template object fully configured with
    the number of nodes requested.
    """
    template = Template()
    template.set_description(
        'Qumulo for AWS has the highest performance of any file storage system '
        'in the public cloud and a complete set of enterprise features, such '
        'as support for SMB, real-time visibility into the storage system, '
        'directory-based capacity quotas, and snapshots.'
    )
    add_conditions(template)
    add_ingress_cidr_param = security_group is None
    add_params(template, add_ingress_cidr_param)

    security_group = security_group or add_security_group(template)

    add_nodes(
        template,
        num_nodes,
        node_name_prefix,
        chassis_spec,
        security_group,
    )
    return template


def parse_args(argv):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter, description=__doc__
    )

    parser.add_argument(
        '--num-nodes', type=int, help='Number of nodes in the cluster', default=4
    )

    parser.add_argument(
        '--config-file',
        type=str,
        required=True,
        help='Config file path specifying volume configuration',
    )

    parser.add_argument(
        '--backing-volume-type-override',
        type=str,
        choices=['sc1', 'st1', 'gp2'],
        help='Override type of EBS volumes for backing storage.',
    )

    parser.add_argument(
        '--security-group',
        type=str,
        help='Specify an existing security group for all network interfaces to use.',
    )

    return parser.parse_args(argv)


class NoBackingVolumesException(Exception):
    pass


def override_backing_type(json_spec, new_type):
    if json_spec.get('backing_spec') is None:
        raise NoBackingVolumesException(
            "The backing volumes' type cannot be set because there are no "
            'backing volumes in the specified config.'
        )
    json_spec['backing_spec']['VolumeType'] = new_type


def generate_qcft(
    num_nodes,
    config_file,
    backing_volume_type_override,
    security_group=None,
):
    with open(config_file) as json_file:
        json_spec = json.load(json_file)

    if backing_volume_type_override is not None:
        override_backing_type(json_spec, backing_volume_type_override)

    chassis_spec = ChassisSpec.from_json(json_spec)
    return create_qumulo_cft(
        num_nodes, 'Qumulo', chassis_spec, security_group
    )


def main(argv):
    options = parse_args(argv)
    cf_template = generate_qcft(
        options.num_nodes,
        options.config_file,
        options.backing_volume_type_override,
        options.security_group,
    )
    print(cf_template.to_json())


if __name__ == '__main__':
    main(sys.argv[1:])
