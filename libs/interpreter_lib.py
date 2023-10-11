"""
This file contains the `Interpreter` class which is responsible for:

- Initializing the interpreter with the necessary configurations and arguments.
- Handling different modes of operation: Code, Script, and Command.
- Generating code based on the user's input and the selected mode.
- Executing the generated code if the user chooses to do so.
- Handling errors during code execution and attempting to resolve them by installing missing packages.
- Cleaning up response files after each iteration.
- Opening resource files such as graphs, charts, and tables generated by the code.
- Logging all important actions and errors for debugging and traceability.
"""

import os
import platform
import subprocess
import time
import webbrowser
from libs.code_interpreter import CodeInterpreter
from litellm import completion
from libs.logger import initialize_logger
from libs.markdown_code import display_code, display_markdown_message
from libs.package_installer import PackageInstaller
from libs.utility_manager import UtilityManager
from dotenv import load_dotenv
        
class Interpreter:
    logger = None
    client = None
    interpreter_version = "1.3"
    
    def __init__(self, args):
        self.args = args
        self.history = []
        self.utility_manager = UtilityManager()
        self.code_interpreter = CodeInterpreter()
        self.package_installer = PackageInstaller()
        self.logger = initialize_logger("logs/interpreter.log")
        self.client = None
        self.config_values = None
        self.system_message = ""
        self.initialize()

    def _open_resource_file(self,filename):
        try:
            if os.path.isfile(filename):
                if platform.system() == "Windows":
                    subprocess.call(['start', filename], shell=True)
                elif platform.system() == "Darwin":
                    subprocess.call(['open', filename])
                elif platform.system() == "Linux":
                    subprocess.call(['xdg-open', filename])
                self.logger.info(f"{filename} exists and opened successfully")
        except Exception as exception:
            display_markdown_message(f"Error in opening files: {str(exception)}")

    def _clean_responses(self):
        files_to_remove = ['graph.png', 'chart.png', 'table.md']
        for file in files_to_remove:
            try:
                if os.path.isfile(file):
                    os.remove(file)
                    self.logger.info(f"{file} removed successfully")
            except Exception as e:
                print(f"Error in removing {file}: {str(e)}")
    
    def _extract_content(self,output):
        try:
            return output['choices'][0]['message']['content']
        except (KeyError, TypeError) as e:
            self.logger.error(f"Error extracting content: {str(e)}")
            raise
    
    def initialize(self):
        self.INTERPRETER_LANGUAGE = self.args.lang if self.args.lang else 'python'
        self.SAVE_CODE = self.args.save_code
        self.EXECUTE_CODE = self.args.exec
        self.DISPLAY_CODE = self.args.display_code
        self.INTERPRRETER_MODEL = self.args.model if self.args.model else None
        self.logger.info(f"Interpreter args model selected is '{self.args.model}")
        self.logger.info(f"Interpreter model selected is '{self.INTERPRRETER_MODEL}")
        self.system_message = ""
        # Open file system_message.txt to a variable system_message
        try:
            with open('system/system_message.txt', 'r') as file:
                self.system_message = file.read()
                if self.system_message != "":
                    self.logger.info(f"System message read successfully")
        except Exception as exception:
            self.logger.error(f"Error occurred while reading system_message.txt: {str(exception)}")
            raise
        
        # Initialize client and mode.
        self.initialize_client()
        self.initialize_mode()
        
        try: # Make this as optional step to have readline history.
            self.utility_manager.initialize_readline_history()
        except:
            self.logger.error(f"Exception on initializing readline history")

    def initialize_client(self):
        load_dotenv()
        hf_model_name = ""
        self.logger.info("Initializing Client")
        
        self.logger.info(f"Interpreter model selected is '{self.INTERPRRETER_MODEL}")
        if self.INTERPRRETER_MODEL is None or self.INTERPRRETER_MODEL == "":
            self.logger.info("HF_MODEL is not provided, using default model.")
            self.INTERPRRETER_MODEL = self.INTERPRRETER_MODEL
            hf_model_name = self.INTERPRRETER_MODEL.strip().split("/")[-1]
            config_file_name = f"configs/gpt-3.5-turbo.config" # Setting default model to GPT 3.5 Turbo.
        else:
            config_file_name = f"configs/{self.INTERPRRETER_MODEL}.config"
        
        self.logger.info(f"Reading config file {config_file_name}")    
        self.config_values = self.utility_manager.read_config_file(config_file_name)
        self.INTERPRRETER_MODEL = str(self.config_values.get('HF_MODEL', self.INTERPRRETER_MODEL))       
        hf_model_name = self.INTERPRRETER_MODEL.strip().split("/")[-1]
        
        self.logger.info(f"Using model {hf_model_name}")
        
        if "gpt" in self.INTERPRRETER_MODEL:
            # Inform user about Heaven-GPT
            display_markdown_message("**GPT 3.5** is provided by **Heaven-GPT**, A Private **GPT** made exclusive for this code-interpreter.")
            # Ask if user wants to read the terms and agreements
            confirmation = input("Do you want to read the terms and agreements before using Heaven-GPT? (Y/N): ")
            if confirmation.lower() == 'y':
                url = "https://heaven-gpt.haseebmir.repl.co/privacy"
                display_markdown_message(f"You can read the terms and agreements here: {url}")
                webbrowser.open(url)
            # Ask for user's agreement to the terms and conditions
            confirmation = input("Do you agree to the terms and conditions? (Y/N): ")
            if confirmation.lower() != 'y':
                self.logger.info("User does not agree to the terms and conditions. Exiting...")
                exit(1)
            else:
                self.logger.info("User agrees to the terms and conditions.")
                return # Skip reading from .env file
            
        # Read the token from the .env file
        hf_token = os.getenv('HUGGINGFACE_API_KEY')
        if not hf_token:
            raise Exception("HuggingFace token not found in .env file.")
        elif not hf_token.startswith('hf_'):
            raise Exception("HuggingFace token should start with 'hf_'. Please check your .env file.")

    def initialize_mode(self):
        self.CODE_MODE = True if self.args.mode == 'code' else False
        self.SCRIPT_MODE = True if self.args.mode == 'script' else False
        self.COMMAND_MODE = True if self.args.mode == 'command' else False
        if not self.SCRIPT_MODE and not self.COMMAND_MODE:
            self.CODE_MODE = True
    
    def get_prompt(self,message: str, chat_history: list[tuple[str, str]]) -> str:
        system_message = None
        
        if self.CODE_MODE:
            system_message = self.system_message
        elif self.SCRIPT_MODE:
            system_message = "Please generate a well-written script that is precise, easy to understand, and compatible with the current operating system."
        elif self.COMMAND_MODE:
            system_message = "Please generate a single line command that is precise, easy to understand, and compatible with the current operating system."
            
        messages = [
            {"role": "system", "content":system_message},
            {"role": "assistant", "content": "Please generate code wrapped inside triple backticks known as codeblock."},
            {"role": "user", "content": message}
        ]
        return messages
    
    def generate_text(self,message, chat_history: list[tuple[str, str]], temperature=0.1, max_tokens=1024,config_values=None):
        self.logger.debug("Generating code.")
        
        # Use the values from the config file if they are provided
        if config_values:
            temperature = float(config_values.get('temperature', temperature))
            max_tokens = int(config_values.get('max_tokens', max_tokens))

        # Get the system prompt
        messages = self.get_prompt(message, chat_history)
        
         # Call the completion function
         
        
        if 'huggingface/' not in self.INTERPRRETER_MODEL and 'gpt' not in self.INTERPRRETER_MODEL:
            self.INTERPRRETER_MODEL = 'huggingface/' + self.INTERPRRETER_MODEL

        # Check if the model is gpt-3.5-turbo
        if 'gpt-3.5-turbo' in self.INTERPRRETER_MODEL:
            # Set environment variables
            os.environ["OPENAI_API_KEY"] = "Ignore the Key." 
            # Set the API base URL
            api_base = "https://heaven-gpt.haseebmir.repl.co" # This is private GPT by Heaven make sure you understand the terms and conditions.
            # Set the custom language model provider
            custom_llm_provider = "openai"
            # Call the chat completions - OpenAI,PALM-2
            output = completion(self.INTERPRRETER_MODEL, messages=messages,temperature=0.1,max_tokens=2048,api_base=api_base,custom_llm_provider=custom_llm_provider)
        else:
            # Call the chat completions - Hugging Face Models.
            output = completion(self.INTERPRRETER_MODEL, messages=messages,temperature=temperature,max_tokens=max_tokens)
        
        self.logger.info(f"Generated text {output}")
        generated_text = self._extract_content(output)
        self.logger.info(f"Generated content {generated_text}")
        return generated_text

    def handle_code_mode(self, task, os_name):
        prompt = f"Generate the code in {self.INTERPRETER_LANGUAGE} language for this task '{task} for Operating System: {os_name}'."
        self.history.append((task, prompt))
        return prompt

    def handle_script_mode(self, task, os_name):
        language_map = {'macos': 'applescript', 'linux': 'bash', 'windows': 'powershell'}
        self.INTERPRETER_LANGUAGE = language_map.get(os_name.lower(), 'python')
        
        script_type = 'Apple script' if os_name.lower() == 'macos' else 'Bash Shell script' if os_name.lower() == 'linux' else 'Powershell script' if os_name.lower() == 'windows' else 'script'
        prompt = f"\nGenerate {script_type} for this prompt and make this script easy to read and understand for this task '{task} for Operating System is {os_name}'."
        return prompt

    def handle_command_mode(self, task, os_name):
        prompt = f"Generate the single terminal command for this task '{task} for Operating System is {os_name}'."
        return prompt

    def handle_mode(self, task, os_name):
        if self.CODE_MODE:
            return self.handle_code_mode(task, os_name)
        elif self.SCRIPT_MODE:
            return self.handle_script_mode(task, os_name)
        elif self.COMMAND_MODE:
            return self.handle_command_mode(task, os_name)

    def execute_code(self, extracted_code, os_name):
        execute = 'y' if self.EXECUTE_CODE else input("Execute the code? (Y/N): ")
        if execute.lower() == 'y':
            try:
                code_output, code_error = "", ""
                if self.SCRIPT_MODE:
                    code_output, code_error = self.code_interpreter.execute_script(extracted_code, os_type=os_name)
                elif self.COMMAND_MODE:
                    code_output, code_error = self.code_interpreter.execute_command(extracted_code)
                elif self.CODE_MODE:
                    code_output, code_error = self.code_interpreter.execute_code(extracted_code, language=self.INTERPRETER_LANGUAGE)
                return code_output, code_error
            except Exception as exception:
                self.logger.error(f"Error occurred while executing code: {str(exception)}")
                return None, str(exception)  # Return error message as second element of tuple
        else:
            return None, None  # Return None, None if user chooses not to execute the code

    def interpreter_main(self):
        
        print(f"Code Interpreter - v{self.interpreter_version}")
        os_platform = self.utility_manager.get_os_platform()
        os_name = os_platform[0]
        command_mode = 'Code'
        mode = 'Script' if self.SCRIPT_MODE else 'Command' if self.COMMAND_MODE else 'Code'
        
        display_code(f"OS: '{os_name}', Language: '{self.INTERPRETER_LANGUAGE}', Mode: '{mode}' Model: '{self.INTERPRRETER_MODEL}'")
        
        command_mode = mode
        start_sep = str(self.config_values.get('start_sep', '```'))
        end_sep = str(self.config_values.get('end_sep', '```'))
        skip_first_line = self.config_values.get('skip_first_line', 'False') == 'True'
        
        self.logger.info(f"Start separator: {start_sep}, End separator: {end_sep}, Skip first line: {skip_first_line}")
        current_time = time.strftime("%H:%M:%S", time.localtime())
        
        while True:
            try:
                
                task = input("> ")
                if task.lower() in ['exit', 'quit']:
                    break
                prompt = self.handle_mode(task, os_name)
                
                # Clean the responses
                self._clean_responses()
                
                # If graph were requested.
                if 'graph' in prompt.lower():
                    if self.INTERPRETER_LANGUAGE == 'python':
                        prompt += "\n" + "using Python use Matplotlib save the graph in file called 'graph.png'"
                    elif self.INTERPRETER_LANGUAGE == 'javascript':
                        prompt += "\n" + "using JavaScript use Chart.js save the graph in file called 'graph.png'"

                # if Chart were requested
                if 'chart' in prompt.lower() or 'plot' in prompt.lower():
                    if self.INTERPRETER_LANGUAGE == 'python':
                        prompt += "\n" + "using Python use Plotly save the chart in file called 'chart.png'"
                    elif self.INTERPRETER_LANGUAGE == 'javascript':
                        prompt += "\n" + "using JavaScript use Chart.js save the chart in file called 'chart.png'"

                # if Table were requested
                if 'table' in prompt.lower():
                    if self.INTERPRETER_LANGUAGE == 'python':
                        prompt += "\n" + "using Python use Pandas save the table in file called 'table.md'"
                    elif self.INTERPRETER_LANGUAGE == 'javascript':
                        prompt += "\n" + "using JavaScript use DataTables save the table in file called 'table.html'"
                    
                self.logger.info(f"Prompt: {prompt}")
                generated_output = self.generate_text(prompt, self.history, config_values=self.config_values)
                
                self.logger.info(f"Generated output type {type(generated_output)}")
                extracted_code = self.code_interpreter.extract_code(generated_output, start_sep, end_sep, skip_first_line)
                
                self.logger.info(f"Extracted code: {extracted_code[:50]}")

                
                if self.DISPLAY_CODE:
                    display_code(extracted_code)
                    self.logger.info("Code extracted successfully.")
                
                if extracted_code:
                    
                    if self.INTERPRETER_LANGUAGE == 'javascript' and self.SAVE_CODE:
                        self.code_interpreter.save_code(f"output/code_generated_{current_time}.js", extracted_code)
                        self.logger.info(f"JavaScript code saved successfully.")
                    
                    elif self.INTERPRETER_LANGUAGE == 'python' and self.SAVE_CODE:
                        self.code_interpreter.save_code(f"output/code_generated_{current_time}.py", extracted_code)
                        self.logger.info(f"Python code saved successfully.")
                    
                    # Execute the code if the user has selected.
                    code_output, code_error = self.execute_code(extracted_code, os_name)
                    
                    if code_output:
                        self.logger.info(f"{self.INTERPRETER_LANGUAGE} code executed successfully.")
                        display_code(code_output)
                        self.logger.info(f"Output: {code_output[:100]}")
                    elif code_error:
                        self.logger.info(f"Python code executed with error.")
                        display_markdown_message(f"Error: {code_error}")
                        
                    # install Package on error.
                    error_messages = ["ModuleNotFound", "ImportError", "No module named", "Cannot find module"]
                    if code_error is not None and any(error_message in code_error for error_message in error_messages):
                        package_name = self.package_installer.extract_package_name(code_error, self.INTERPRETER_LANGUAGE)
                        if package_name:
                            self.logger.info(f"Installing package {package_name} on interpreter {self.INTERPRETER_LANGUAGE}")
                            self.package_installer.install_package(package_name, self.INTERPRETER_LANGUAGE)

                    try:
                        # Check if graph.png exists and open it.
                        self._open_resource_file('graph.png')
                        
                        # Check if chart.png exists and open it.
                        self._open_resource_file('chart.png')
                        
                        # Check if table.md exists and open it.
                        self._open_resource_file('table.md')
                    except Exception as exception:
                        display_markdown_message(f"Error in opening resource files: {str(exception)}")
                
                self.utility_manager.save_history_json(task, command_mode, os_name, self.INTERPRETER_LANGUAGE, prompt, extracted_code, self.INTERPRRETER_MODEL)
                
            except Exception as exception:
                import traceback
                traceback.print_exc()
                self.logger.error(f"Error occurred: {str(exception)}")
                raise exception