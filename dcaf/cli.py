#!/usr/bin/env python3
"""
DAB CLI - DuploCloud Agent Builder command line interface to run helper scripts
"""
import subprocess
import json
import os
import sys
import argparse
import shutil
from pathlib import Path
import dotenv

def env_update_aws_creds(tenant=None, host=None):
    """Update .env file with AWS credentials from DuploCloud."""
    # Use env vars as defaults
    tenant = tenant or os.environ.get('DUPLO_TENANT')
    host = host or os.environ.get('DUPLO_HOST')
    
    if not tenant:
        print("Error: Tenant not specified. Set DUPLO_TENANT env var or use --tenant flag")
        return 1
    
    if not host:
        print("Error: Host not specified. Set DUPLO_HOST env var or use --host flag")
        return 1
    
    print(f"Using tenant: {tenant}")
    print(f"Using host: {host}")
    
    # Check prerequisites
    if not shutil.which('duplo-jit'):
        print("Error: duplo-jit is not installed or not in PATH")
        print("Please install duplo-jit: https://docs.duplocloud.com/docs/overview/use-cases/jit-access#step-1.-install-duplo-jit")
        return 1
    
    # Run duplo-jit
    try:
        print("Fetching AWS credentials using duplo-jit...")
        result = subprocess.run(
            ['duplo-jit', 'aws', '--no-cache', f'--tenant={tenant}', '--host', host, '--interactive'],
            capture_output=True,
            text=True,
            check=True
        )
        
        creds = json.loads(result.stdout)
        
        # Update .env file
        env_file = Path('.env')
        env_vars = {}
        
        # Read existing .env if it exists
        if env_file.exists():
            print(f"Updating existing .env file...")
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        env_vars[key] = value
        else:
            print(f"Creating new .env file...")
        
        # Update AWS credentials
        env_vars['AWS_ACCESS_KEY_ID'] = f'"{creds["AccessKeyId"]}"'
        env_vars['AWS_SECRET_ACCESS_KEY'] = f'"{creds["SecretAccessKey"]}"'
        env_vars['AWS_SESSION_TOKEN'] = f'"{creds["SessionToken"]}"'
        
        # Write back to .env
        with open(env_file, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}={value}\n')
        
        print(f"✅ AWS credentials updated in {env_file.absolute()}")
        print("⚠️  Make sure .env is in your .gitignore!")
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"Error running duplo-jit: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return 1
    except json.JSONDecodeError as e:
        print(f"Error parsing duplo-jit output: {e}")
        print("Make sure duplo-jit is properly configured")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


def docker_build_push_ecr(tag, repo_name=None, registry=None, aws_profile=None, region=None, dockerfile='Dockerfile'):
   """Build and push Docker image to ECR."""
   # Use env vars as defaults (following AWS conventions)
   repo_name = repo_name or os.environ.get('ECR_REPOSITORY_NAME')
   registry = registry or os.environ.get('ECR_REGISTRY')
   region = region or os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
   
   # Validate required inputs
   if not repo_name:
       print("Error: Repository name not specified. Set ECR_REPOSITORY_NAME env var or use --repo-name flag")
       return 1
       
   if not registry:
       print("Error: ECR registry not specified. Set ECR_REGISTRY env var or use --registry flag")
       return 1
   
   # Check prerequisites
   if not shutil.which('docker'):
       print("Error: Docker is not installed or not in PATH")
       return 1
   
   if not shutil.which('aws'):
       print("Error: AWS CLI is not installed or not in PATH")
       return 1
   
   # Check if Dockerfile exists
   dockerfile_path = Path(dockerfile)
   if not dockerfile_path.exists():
       print(f"Error: Dockerfile not found at {dockerfile_path.absolute()}")
       return 1
   
   # Build profile option
   profile_opt = f"--profile {aws_profile}" if aws_profile else ""
   
   try:
       # Step 1: Authenticate Docker to ECR
       print(f"\n[1/4] Authenticating Docker to ECR registry...")
       auth_cmd = f"aws ecr get-login-password --region {region} {profile_opt} | docker login --username AWS --password-stdin {registry}"
       print(f"Running: {auth_cmd}")
       
       # Run auth command through shell to handle pipe
       result = subprocess.run(auth_cmd, shell=True, capture_output=True, text=True)
       if result.returncode != 0:
           print(f"Error authenticating to ECR: {result.stderr}")
           return 1
       print("✓ Successfully authenticated to ECR")
       
       # Step 2: Build image
       print(f"\n[2/4] Building Docker image...")
       build_cmd = ['docker', 'build', '-t', f"{repo_name}:{tag}", '-f', dockerfile, '.']
       print(f"Running: {' '.join(build_cmd)}")
       
       subprocess.run(build_cmd, check=True)
       print(f"✓ Successfully built {repo_name}:{tag}")
       
       # Step 3: Tag for ECR
       ecr_image = f"{registry}/{repo_name}:{tag}"
       print(f"\n[3/4] Tagging image for ECR...")
       tag_cmd = ['docker', 'tag', f"{repo_name}:{tag}", ecr_image]
       print(f"Running: {' '.join(tag_cmd)}")
       
       subprocess.run(tag_cmd, check=True)
       print(f"✓ Tagged as {ecr_image}")
       
       # Step 4: Push to ECR
       print(f"\n[4/4] Pushing to ECR...")
       push_cmd = ['docker', 'push', ecr_image]
       print(f"Running: {' '.join(push_cmd)}")
       
       subprocess.run(push_cmd, check=True)
       
       print(f"\n✅ Successfully pushed {ecr_image}")
       return 0
       
   except subprocess.CalledProcessError as e:
       print(f"\nError: Command failed with exit code {e.returncode}")
       return 1
   except Exception as e:
       print(f"\nUnexpected error: {e}")
       return 1


def deploy_agent(agent_name, token=None):
    """Deploy agent using DuploCloud API."""
    token = token or os.environ.get('DUPLO_TOKEN')
    
    if not token:
        print("Error: Token not specified. Set DUPLO_TOKEN env var or use --token flag")
        return 1
    
    print(f"Deploying agent: {agent_name}")
    # TODO: Implement actual deployment logic
    print("Deploy agent functionality not yet implemented")
    return 0

def main():
    dotenv.load_dotenv(override=True)
    
    parser = argparse.ArgumentParser(
        prog='dcaf',
        description='DuploCloud Agent Builder CLI'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # env-update-aws-creds command
    env_parser = subparsers.add_parser(
        'env-update-aws-creds',
        help='Update AWS credentials in .env file from DuploCloud'
    )
    env_parser.add_argument('--tenant', help='DuploCloud tenant name (or set DUPLO_TENANT)')
    env_parser.add_argument('--host', help='DuploCloud host URL (or set DUPLO_HOST)')


    # docker-build-push-ecr command
    docker_parser = subparsers.add_parser(
        'docker-build-push-ecr',
        help='Build and push Docker image to Amazon ECR'
    )
    docker_parser.add_argument('tag', help='Image tag (e.g., latest, v1.0.0)')
    docker_parser.add_argument('--repo-name', help='ECR repository name (or set ECR_REPOSITORY_NAME)')
    docker_parser.add_argument('--registry', help='ECR registry URI (or set ECR_REGISTRY)')
    docker_parser.add_argument('--aws-profile', help='AWS profile to use')
    docker_parser.add_argument('--region', help='AWS region (or set AWS_DEFAULT_REGION)')
    docker_parser.add_argument('--dockerfile', default='Dockerfile', help='Path to Dockerfile (default: Dockerfile)')    


    # deploy-agent command
    deploy_parser = subparsers.add_parser(
        'deploy-agent',
        help='Deploy agent to DuploCloud'
    )
    deploy_parser.add_argument('agent_name', help='Name of the agent to deploy')
    deploy_parser.add_argument('--token', help='DuploCloud API token (or set DUPLO_TOKEN)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Show help if no command provided
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Route to appropriate function
    exit_code = 1
    if args.command == 'env-update-aws-creds':
        exit_code = env_update_aws_creds(args.tenant, args.host)
        
    elif args.command == 'docker-build-push-ecr':
        exit_code = docker_build_push_ecr(
            args.tag,
            args.repo_name,
            args.registry,
            args.aws_profile,
            args.region,
            args.dockerfile)

    elif args.command == 'deploy-agent':
        exit_code = deploy_agent(args.agent_name, args.token)
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()