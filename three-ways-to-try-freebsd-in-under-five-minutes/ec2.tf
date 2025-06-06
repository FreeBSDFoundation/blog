# https://registry.terraform.io/providers/hashicorp/aws/latest/docs
# you'll want to change the default region
provider "aws" {
  profile = "default"
  region = "eu-west-2"
}

# Find the AMI ID
data "aws_ami" "freebsd" {
  most_recent = true
  owners = ["782442783595"]
  filter {
    name   = "name"
    values = ["FreeBSD*14.2-RELEASE*small*ZFS"]
  }
  filter {
    name   = "architecture"
    values = ["arm64"]
  }
  # Want to do some testing with none stable releases?
  #filter {
  #  name   = "name"
  #  values = ["FreeBSD*14.0-ALPHA2*ZFS"]
  #}
  # owners = ["782442783595"]  
}

# Informational. Could comment this out if you want.
output "freebsd_ami_id" {
  value = data.aws_ami.freebsd.id
}

# Variables. Create terraform.tfvars or pass --var var=VALUE to terraform apply
variable "num" {
  default = 1
  description = "Number of ec2 instances to run"
}

variable "type" {
  description = "t4g.nano 512mb; .micro 1gb; .medium 4gb x2gd.medium cheapest 16gb"
}

variable "key" {
  description = "SSH key name. Must exist in ec2"
}

variable "root_disk" {
  description = "Root disk size"
}

# https://aws.amazon.com/marketplace/pp/prodview-sxzreyutwngxy
# some useful tools for developing this configuration
# aws cli to find ami IDs:
# aws ec2 describe-images --filters "Name=name,Values=*FreeBSD*" "Name=state,Values=available" --region eu-west-2 --query 'sort_by(Images[*], &CreationDate)[*].{Architecture: Architecture, CreationDate: CreationDate, OwnerId: OwnerId, ImageId: ImageId, Name: Name}' --output table
#
# also handy:
# aws ec2 describe-instance-types  --region eu-west-2 --query "InstanceTypes[?starts_with(InstanceType, 't4g')].[InstanceType, MemoryInfo.SizeInMiB]" --output json | jq '.[] | [.[0], .[1] / 1024]'

resource "aws_instance" "nodes" {
    # bump size on root disk
    ebs_block_device {
      device_name = "/dev/sda1"
      volume_size = var.root_disk
      volume_type = "gp2"
      delete_on_termination = true
    }
  count         = var.num
  ami           = data.aws_ami.freebsd.id
  instance_type = var.type
  key_name      = var.key
  user_data     = <<-EOF
#!/bin/sh
echo 'firstboot_pkgs_list="python3"' >> /etc/rc.conf
EOF
  # don't force-recreate instance if only user data changes
  lifecycle {
    ignore_changes = [user_data]
  }
}

# if you want to add an extra disk at a later point 
# resource "aws_ebs_volume" "storage" {
#   availability_zone = aws_instance.nodes[0].availability_zone
#   size              = 10
#   tags = {
#     Name = "storage"
#   }
# }
# 
# resource "aws_volume_attachment" "ebs_att_1" {
#   device_name = "/dev/sdh"
#   volume_id   = aws_ebs_volume.storage.id
#   instance_id = aws_instance.nodes[0].id
# }

output "instance_public_dns" {
  value = aws_instance.nodes.*.public_dns
}

