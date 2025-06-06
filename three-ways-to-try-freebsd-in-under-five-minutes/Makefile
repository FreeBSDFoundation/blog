.PHONY: default inventory

host := $(shell terraform output -json instance_public_dns | jq -r '.[]')

default:
	@echo $(host)
	
inventory:
	@yq -i ".all.hosts.ec2.ansible_host = \"$(host)\"" inventory.yml

