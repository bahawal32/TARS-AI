from fastapi import FastAPI,  Response
import time
import os
from openai import OpenAI
from dotenv import load_dotenv
import json
from gekko_db import GekkoDB
from tokenizer import tokenize_string
from real_time_search import search_online, search_online_desc
import json
import logging
logger = logging.getLogger(__name__)

load_dotenv()

# Access API key
ASSISTANT_ID = os.getenv("TARS_ASSISTANT_ID")
api_key = os.getenv("TARS_OPENAI")
GEKKO_API_KEY = os.getenv("GEKKO_API_KEY")
client = OpenAI(
    api_key=api_key,
)

app = FastAPI()

gekko_client = GekkoDB(GEKKO_API_KEY)

# Enter your Assistant ID here.
# print(ASSISTANT_ID,'...............')
STORE_ID = os.getenv("TARS_DB")
# Access API key
# api_key = os.getenv("OPENAI_KEY_OUTLOOK")
client = OpenAI(
    api_key=api_key,
)
tools_list = [
		{
		"type":"function",
		"function": search_online_desc
		},
		{
		"type": "function",
		"function":gekko_client.get_coin_data_by_id_desc
		},

		{
		"type": "function",
		"function": gekko_client.get_coin_historical_chart_data_by_id_desc
        },

		{
		"type": "function",
		"function": gekko_client.get_trend_search_desc
		},
		{
		"type": "function",
		"function": gekko_client.get_coin_historical_data_by_id_desc
		}
		]

assistant = client.beta.assistants.update(
	assistant_id=ASSISTANT_ID,
	tool_resources={"file_search": {"vector_store_ids": [STORE_ID]}},
	tools = tools_list,
	instructions = "Please address yourself as Alex an web3 assistant and don't answer more than 250 words.  You are ALEX made by TARS AI, and always search for recent data online rather than from your memory"
	)

def get_outputs_for_tool_call(tool_call):
	coin_id = json.loads(tool_call.function.arguments['coin_id'])
	details = gekko_client.get_coin_data_by_id(coin_id)
	return {"tool_call_id": tool_call.id,
		 "output": details
		 }

DATA = None


@app.post("/ask/")
async def ask_question(question: str, user_id: str,token: str, thread_id: str=None, ):
	if token != '1MillionDollars':
		return Response(status_code=200, content="Invalid Token!")

	if len(tokenize_string(question)) > 200:
		return Response(status_code=200, content="Question is too long. Please shorten your question and try again.")

	
	# Upload the user provided file to OpenAI

	# Create a thread and attach the file to the message
	try:
		if thread_id is not None:
			print(thread_id, 'received thread')
			thread = client.beta.threads.retrieve(thread_id)
		else:
			thread = client.beta.threads.create()
			print(thread.id, 'creating thread')
	except:
		thread = client.beta.threads.create()
		print(thread.id, 'could not retrive the provided thread making a new one')


	
	message = client.beta.threads.messages.create(
		thread_id=thread.id,
		role="user",
        content=f"{question}",

	)

	run = client.beta.threads.runs.create_and_poll(
		thread_id=thread.id, assistant_id=assistant.id,
		instructions="Please address yourself as Alex an web3 assistant and don't answer more than 250 words.  Always address yourself as ALEX made by TARS AI, and always search for recent data online rather than from your memory "
	)

	run_status = client.beta.threads.runs.retrieve(
        thread_id=thread.id,
        run_id=run.id
   		)
	output = "NULL"
	func_name = "NULL"
	chart = False
	if any(item in ['chart', 'plot','Chart','Plot', 'graph', 'Graph'] for item in  question.split(' ')):
		chart = True


	while run_status.status != 'completed':
		run_status = client.beta.threads.runs.retrieve(
        thread_id=thread.id,
        run_id=run.id)
		try:
			if run_status.status == 'requires_action':
				required_actions = run_status.required_action.submit_tool_outputs.model_dump()
				tool_outputs = []
				for action in required_actions["tool_calls"]:
					func_name = action['function']['name']
					logger.info("func_name:" + func_name)
					arguments = json.loads(action['function']['arguments'])
					logger.info(f"received args: {arguments}")

					if func_name == "get_coin_data_by_id":
						output = gekko_client.get_coin_data_by_id(coin_id=arguments['coin_id'])
						tool_outputs.append(
									{
									"tool_call_id": action['id'],
									"output": f'query: {output}'
									}
						)
						
					if func_name == "get_coin_historical_data_by_id":
						output = gekko_client.get_coin_historical_data_by_id(coin_id=arguments['coin_id'], date=arguments['date'], )
						tool_outputs.append(
									{
									"tool_call_id": action['id'],
									"output": f'query: {output}'
									}
								)
					
					if func_name == "get_coin_historical_chart_data_by_id":
						
						output = gekko_client.get_coin_historical_chart_data_by_id(coin_id=arguments['coin_id'], data_type=arguments.get('data_type', 'price'),days=arguments['days'], interval=arguments.get('interval', 'daily'), currency=arguments.get('currency','USD'))
						tool_outputs.append(
									{
									"tool_call_id": action['id'],
									"output": f'query: {output}',
									}
						)
						data_type = arguments.get('data_type', 'price')
						global DATA
						DATA = {'data_type':data_type, 'values':output[data_type]}
						logger.info(f"Data type: {data_type} values: {output[data_type]}")
						print('data fron hist chart', DATA)
					if func_name == "get_trend_search":
						output = gekko_client.get_trend_search()
						tool_outputs.append(
									{
									"tool_call_id": action['id'],
									"output": f'query: {output}'
									}
								)
					if func_name == "search_online":
						output = search_online(question=arguments['question'])
						tool_outputs.append(
							{
								"tool_call_id": action['id'],
								"output": f'query: {output}'
							}
						)
	
					print("Submitting outputs back to the Assistant...")
					print('tools output', tool_outputs )
					client.beta.threads.runs.submit_tool_outputs(
						thread_id=thread.id,
						run_id=run.id,
						tool_outputs=tool_outputs,
					)
		except Exception as e:
			logger.error("Failed to process output", e)
			return {'answer':"I am unable to understand your question can you be more specific?", "thread_id":thread.id}



		   
	messages = client.beta.threads.messages.list(thread_id=thread.id)
	for msg in messages.data:
		try:
			content = msg.content[0].text.value
			return {'answer':content, "thread_id":thread.id, "function":func_name,"chart": chart, 'data': DATA }
		except Exception as e: 
			print(e)
			return {'answer':"I am unable to understand your question can you be more specific?", "thread_id":thread.id}