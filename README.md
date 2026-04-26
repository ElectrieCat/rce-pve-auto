## Introduction
I've coded this with AI using Google Gemini chat due to limited time to deploy on production and lack of required python programming knowledge

If you find a bug or make some code enchantment for this tool, please consider making issue or pull request, I'd try to find free time to merge it.

From my perspective, there's been "enough" testing on most dangerous operations performed by this tool, but there is no guarantees to use it in production, always make backups of the tool using inbuilt subcommand before doing something massive and pay attention to commands you run and config changes you make.

## Installation
Firstly, this tool was built to use with linux, no windows compatibility planned, though one can try running it in git bash or something similar on windows

You must have installed terraform in your system path so it's available to be called from anywhere

Also, you must have python3 installed

### Installing requirements and verifying terraform availability
```
python3 requirements.py 
```
### Usage
```
python manager.py -h
```
```
Proxmox Lab Automation Manager

positional arguments:
  {change-password,parse-test,deploy-users,deploy-lab,destroy-lab,backup}
    change-password     Change password for a user or entire group
    parse-test          Test parsing of users.yaml config
    deploy-users        Deploy users and resource pools
    deploy-lab          Deploy a specific lab for all permitted users
    destroy-lab         Destroy labs marked with destroy: true in YAML
    backup              Create a system backup archive

options:
  -h, --help            show this help message and exit
```
Few of those arguments have their own help message, you can access it by executing
```
python manager.py change-password -h
```
All conf files and lab example have documentation on their format and behaviour in comments, here's the brief overview and exaplanation of specific behaviour 

First of all, you should configure config/auth.yaml
Then make up your users.yaml and deploy it by running
```
python manager.py deploy-users GROUP
```
This subcommand behaviour is different from deploying labs, when you remove/comment out user/group from users.yaml, it will try to delete it from proxmox upon execution

Deletion safety is present, but anyways you must double check what you've done to the config before deploying it

Group won't be destroyed if there's any user directory under 'groups/example-group' directory

User won't be destroyed if there's any lab directory under 'groups/example-group/users/UserEX/labs/'

Each time you change users.yaml and deploy it, the changes will be passed down to the objects and terraform executioner, so you can dynamically update user states like 'permit' when you need to

If you want to remove all groups and users, comment out or delete them from config starting right after 'groups' level and run
```
python manager.py deploy-users ANY_WORD
```

When you've done with setting up your groups and users, you can go for labs configuraton and deploy

First of all, configure 'configs/labs.yaml'
Then you must create lab folder with your lab name under 'configs/labs/'

Configure it in any way that terraform's bpg provider is compatible with, you can find docs at https://registry.terraform.io/providers/bpg/proxmox/latest/docs

Verify that you've done everything correctly before actually deploying lab

This won't show snapshot creation info during plan creation
```
python manager.py deploy-lab LAB_NAME --plan
```

Deploy or update your lab configuration by running

```
python manager.py deploy-lab LAB_NAME
```

To destroy labs you should understand the logic of 'destroy' and 'unmanaged' options first, it's documented right in the 'labs.yaml' file itself

Before destroying your labs, as there is no undo, you must check what will happen before you actually do this

```
python manager.py destroy-lab LAB_NAME --plan
```

After you checked it, run this

```
python manager.py destroy-lab LAB_NAME
```

P.S. My apologies for messy code in most places, the refactoring is planned someday in the future.