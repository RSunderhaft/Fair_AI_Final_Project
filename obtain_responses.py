
import json
import pandas as pd
import random
import asyncio

import time
from argparse import ArgumentParser
import openai
import torch
from openai import AsyncOpenAI
from codetiming import Timer
import os
from dotenv import load_dotenv
from tqdm import tqdm

from system_prompts import PROMPTS as SYSTEM_PROMPTS

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", default="Key Not Available")

def arguments():
    parser = ArgumentParser('Toxcity_Experiment_One')

    parser.add_argument('--model_name', '-mn',
                        default="gpt-4-1106-preview", type=str,
                        metavar='MN', help='Which model to run experiment on')

    parser.add_argument('--prompt_type', '-pt',
                        default = "toxic", type = str,
                        metavar = "PT", help = "Which prompt type to run 'toxic' or 'nontoxic'")
    
    parser.add_argument('--experiment_num', '-exp_num',
                        default = 1, type = int,
                        metavar = "EXP-NUM", help = "Enter a number '1' or '2' to denote which experiment you want to run.")

    parser.add_argument('--num_seeds', '-ns',
                        default = 1, type = int,
                        metavar = "NS", help = "Enter the amount of seeds you want to have while running program")

    parser.add_argument('--num_prompts', '-np',
                        default = 300, type = int,
                        metavar = "NP", help = "Enter the number of prompts you want for the program")
    
    args = parser.parse_args()

    return vars(args)


##############################################################
### Format Prompts
##############################################################


def create_prompts(system_prompts, user_prompts):

    messages = []

    for prompt in user_prompts:
        for sys_data in system_prompts:

                system_prompt = sys_data["sys_prompt"]
                task_desc = sys_data["task_desc"]
                user_prompt = prompt["prompt"]["text"]

                message = [{"role": "system", "content": system_prompt},
                           {"role": "user", "content": task_desc + user_prompt}]

                meta_data = {"sys_idx" : sys_data["idx"], "user_prompt" : user_prompt}
                
                data = {"meta_data" : meta_data, "message" : message}

                messages.append(data)

    return messages

##############################################################
### API Calls
##############################################################

async def generate_answer(prompt, client, seed = 1):

    message = prompt["message"]

    response = await client.chat.completions.create(model = "gpt-4-1106-preview", 
                                                    messages=message, max_tokens = 100, 
                                                    temperature = 1, top_p = 1, seed = seed)
    
    output = response.choices[0].message.content

    output_dict = {"user_prompt" : prompt["meta_data"]["user_prompt"], "sys_idx" : prompt["meta_data"]["sys_idx"] , "system" : message[0]["content"], "full_prompt" : message[1]["content"], "response" : output, "gen_id" : seed}

    return output_dict


async def execute_batch(batch, client, num_seeds = 1, delay_between_calls = 0.12):

    tasks = []

    for prompt in batch:
        for seed in range(num_seeds):
            task = asyncio.create_task(generate_answer(prompt, client, seed = seed))
            tasks.append(task)

    results = await asyncio.gather(*tasks)

    return results


##############################################################
### Main Loop
##############################################################


async def main():

    args = arguments()

    model_name = args["model_name"]
    prompt_type = args["prompt_type"]
    exp_num = args["experiment_num"]
    num_seeds = args["num_seeds"]
    num_prompts = args["num_prompts"]

    # Load in prompts

    print("Loading Prompts")
    prompts = None
    if prompt_type == "toxic":
        with open('prompts/challenging_prompts.jsonl', 'r') as file:
            prompts = [json.loads(line) for line in file]
    elif prompt_type == "nontoxic":
        with open('prompts/non_toxic_prompts.jsonl', 'r') as file:
            prompts = [json.loads(line) for line in file]
    else:
        raise Exception("Invalid prompt type entered")

    model_client = AsyncOpenAI(api_key = OPENAI_API_KEY)

    print("Creating Prompts")
    
    # Shuffle promtps
    random.seed(1)
    random.shuffle(prompts)

    # Create prompts in proper format
    test_prompts = None
    if exp_num == 1:
        test_prompts = create_prompts(SYSTEM_PROMPTS[:2], prompts[:num_prompts])
    elif exp_num == 2:
        test_prompts = create_prompts(SYSTEM_PROMPTS, prompts[:num_prompts])

    data_columns = ["user_prompt", "sys_idx", "system", "full_prompt", "response", "gen_id"]
    csv_save_path = f"toxicity_experiment_{exp_num}/{prompt_type}_responses_{num_seeds}_seeds_{num_prompts}_prompts.csv"

    print("Obtaining Responses")

    # Data for batching and delays
    batch_size = 100 // num_seeds
    delay_between_batches = 30
    delay_between_calls = 0.12

    timer = Timer(text=f"Text Generation elapsed time: {{:.1f}}")
    timer.start()

    for i in tqdm(range(0, len(test_prompts), batch_size), desc = "Batch Num"):

        batch_prompts = test_prompts[i:i + batch_size]
        results = await execute_batch(batch_prompts, model_client, num_seeds, delay_between_calls)

        new_data = pd.DataFrame(results, columns = data_columns)
        
        print("Writing to CSV")
        new_data.to_csv(csv_save_path, mode="a", header = False, index = False, sep = "\t")

        print("Batch delay in progress")
        await asyncio.sleep(delay_between_batches)
        print("Batch delay done")

    timer.stop()

    print("Done")

if __name__ == '__main__':
    asyncio.run(main())