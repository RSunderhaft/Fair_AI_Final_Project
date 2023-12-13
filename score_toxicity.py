import pandas as pd

import time
from argparse import ArgumentParser
from googleapiclient import discovery
from tqdm import tqdm
from codetiming import Timer

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
PERSPECTIVE_API_KEY = os.getenv("PERSPECTIVE_API_KEY")

###################################################
### ARGS
###################################################

def arguments():
    parser = ArgumentParser('Score Toxicity')

    parser.add_argument("--file_path", "-f_path", 
                        required=True, help="Enter the path to the file you want to obtain a toxicity score for",
                        type=str)
    
    parser.add_argument('--prompt_type', '-pt',
                        default = "toxic", type = str,
                        metavar = "PT", help = "Which prompt type to run 'toxic' or 'nontoxic'")
    
    parser.add_argument('--experiment_num', '-exp_num',
                        default = 1, type = int,
                        metavar = "EXP-NUM", help = "Enter a number '1' or '2' to denote which experiment you want to run.")


    args =  parser.parse_args()

    return vars(args)


###################################################
### API
###################################################

async def perplexity_api_eval(client, text_analyzed, idx):

    analyze_request = {
    'comment': {'text': text_analyzed},
    'requestedAttributes': {'TOXICITY': {}},
    "languages" : ["en"]
    }

    response = client.comments().analyze(body=analyze_request).execute()
    toxicity_value = response["attributeScores"]["TOXICITY"]["summaryScore"]["value"]

    data_output = {"idx" : idx, "text_analyzed" : text_analyzed, "toxicity_score" : toxicity_value}

    return data_output


async def execute_batch(batch, client):

    tasks = []

    for idx, response in enumerate(batch):
            task = asyncio.create_task(perplexity_api_eval(client, response, idx))
            tasks.append(task)

    results = await asyncio.gather(*tasks)

    return results


###################################################
### Main
###################################################

async def main():

    # Create API Client
    api_client = discovery.build(
        "commentanalyzer",
        "v1alpha1",
        developerKey = PERSPECTIVE_API_KEY,
        discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1",
        static_discovery=False)
    
    # Load in CSV
    args = arguments()
    file_path = args["file_path"]
    prompt_type = args["prompt_type"]
    exp_num = args["experiment_num"]

    column_headers = ["user_prompt", "sys_idx", "system", "full_prompt", "response", "gen_id"]
    response_data = pd.read_csv(file_path, sep="\t", names= column_headers)["response"]

    # Need a better way to score the csvs and save them
    csv_save_path = f"toxicity_experiment_{exp_num}/{prompt_type}_scores.csv"

    # Loop through responses and make API call with them
    batch_size = 100
    delay_between_batch = 5

    timer = Timer(text=f"Text Analyze elapsed time: {{:.1f}}")
    timer.start()

    for i in tqdm(range(0, len(response_data), batch_size), desc = "Batches"):

        batch = response_data[i: i + batch_size]

        results = await execute_batch(batch, api_client)

        new_data = pd.DataFrame(results, columns = ["idx", "text_analyzed", "toxicity_score"])
        
        new_data.to_csv(csv_save_path, mode="a", header = False, index = False, sep = "\t")

        await asyncio.sleep(delay_between_batch)
    
    timer.stop()


if __name__ == "__main__":
    asyncio.run(main())