# Transport Emission Measurement (TEM)

# Table of contents
1. [Introduction](#introduction)
2. [Requirements](#requirements)
3. [Running Terraform](#runningTerraform)
    1. [Using Terraform CLI](#terraformCli)
4. [Deployment Considerations](#deployment)
5. [FAQs](#faqs)

# Introduction <a name="introduction"></a>
This creates an ECS task and service to receive the image stored in the ECR created by `tem-infra-config` repository.

# Requirements <a name="requirements"></a>
- Terraform CLI version ~> v1.4.2 (to plan and run terraform)
    - `brew install terraform`
- AWS Permissions to the DEV and PROD accounts
    - https://wiki.int.kn/display/RGS/Set+AWS+CCC+User+profiles
- CCC-AWS configured
    - https://git.int.kn/projects/CCC/repos/ccc-aws/browse
- Environment Variables
    - AWS_REGION="eu-central-1"
    - AWS_PROFILE="<your_env_aws_profile>"
        - Depends on which environment you want to execute

# Running Terraform <a name="runningTerraform"></a>

## Using Terraform CLI <a name="terraformCli"></a>

1. First Step is to Init the terraform
    1. `export AWS_REGION="eu-central-1"`
    2. `export AWS_PROFILE="<your_env_aws_profile>" or
    3. `terraform init -backend-config=environments/<env>/backend.conf`

2. Plan the terraform code
    1. `terraform plan -var-file=environments/<env>/<env>.tfvars`

3. If the plan meets your expectation you need now to apply it:
    1. `terraform apply -var-file=environments/<env>/<env>.tfvars`

**INFORMATION: Change `<env>` placeholder with the environment: `dev` or `prod`**

## Deployment Considerations <a name="deployment"></a>

There are mainly four ways to define parametres for the application:

- Application.properties in the code
- AWS ParameterStore (part of AWS SSM)
- AWS SecretsManager
- Environment Variables in the deployment config

The way it is being used in TEM depends on the scope they have for the environment:
- Application.properties for a parameter, which is the same for all environments (i.e. ECP Endpoint)
- AWS Parameter Store for Parametres, which differ for each environment (i.e. Dev, Prod), like Kafka Connection Strings
  - those are being defined in a separate Terraform Module
- AWS SecretsManager for all kinds of secrets
- Environment Variables for parametres, which are same for each environment and usually close to the container (such as CPU, etc)

## FAQs <a name="FAQs"></a>

1. When: `Error: Backend configuration changed`
    1. Then:  `rm -rf .terraform`
    1. Also: `terraform init -backend-config=environments/<env>/backend.tf`
    1. why: this happens when you init the terraform when you have initiated previously on other environment


# Helpers Terraform
## Init
´´´
terraform -chdir=cicd init -backend-config=environments/dev/backend.conf
´´´
## Plan
´´´
terraform -chdir=cicd plan -var-file=environments/dev/dev.tfvars
´´´
