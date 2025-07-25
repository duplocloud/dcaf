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


def docker_build_push(tag, repo, dockerfile='Dockerfile'):
    """Build and push Docker image to ECR."""
    print(f"Building Docker image with tag: {tag}")
    print(f"Repository: {repo}")
    print(f"Dockerfile: {dockerfile}")
    
    # TODO: Implement actual logic to fetch aws ecr creds etc

    # Check if Docker is installed
    if not shutil.which('docker'):
        print("Error: Docker is not installed or not in PATH")
        return 1
    
    # Check if Dockerfile exists
    if not Path(dockerfile).exists():
        print(f"Error: Dockerfile not found at {dockerfile}")
        return 1
    
    try:
        # Build image
        print(f"Building image...")
        subprocess.run(
            ['docker', 'build', '-t', tag, '-f', dockerfile, '.'],
            check=True
        )
        
        # Tag for ECR
        ecr_tag = f"{repo}:{tag}"
        print(f"Tagging image as {ecr_tag}")
        subprocess.run(
            ['docker', 'tag', tag, ecr_tag],
            check=True
        )
        
        # Push to ECR
        print(f"Pushing to ECR...")
        subprocess.run(
            ['docker', 'push', ecr_tag],
            check=True
        )
        
        print(f"✅ Successfully pushed {ecr_tag}")
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"Error during docker operation: {e}")
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
        prog='dab',
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
    
    # docker-build-push command
    docker_parser = subparsers.add_parser(
        'docker-build-push',
        help='Build and push Docker image to ECR'
    )
    docker_parser.add_argument('tag', help='Docker image tag')
    docker_parser.add_argument('repo', help='ECR repository URL')
    docker_parser.add_argument(
        '--dockerfile', 
        default='Dockerfile',
        help='Path to Dockerfile (default: Dockerfile)'
    )
    
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
    elif args.command == 'docker-build-push':
        exit_code = docker_build_push(args.tag, args.repo, args.dockerfile)
    elif args.command == 'deploy-agent':
        exit_code = deploy_agent(args.agent_name, args.token)
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()