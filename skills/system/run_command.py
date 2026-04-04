# __skill_name__ = "run_command"
# __skill_description__ = "Execute a shell command and return output"
# __skill_active__ = False

import subprocess
import asyncio


async def execute(command: str, timeout: int = 30) -> str:
    """
    Execute a shell command and return output.
    
    Args:
        command: Shell command to execute
        timeout: Command timeout in seconds (default: 30)
        
    Returns:
        Command output or error message
    """
    try:
        # Use asyncio to run the command asynchronously
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        output = ""
        if stdout:
            output += stdout.decode().strip()
        if stderr:
            if output:
                output += "\n"
            output += stderr.decode().strip()
            
        return output if output else "Command executed successfully (no output)"
        
    except asyncio.TimeoutError:
        return f"Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"