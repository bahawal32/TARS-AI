from fastapi import FastAPI,  Response, Header
import time
import os
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv
import json
from gekko_db import GekkoDB
from tokenizer import tokenize_string
from real_time_search import search_online, search_online_desc, current_data_time
import json

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
renew = False
assistant = client.beta.assistants.update(
	assistant_id=ASSISTANT_ID,
	tool_resources={"file_search": {"vector_store_ids": [STORE_ID]}},
	tools = tools_list,
	instructions = f"""
				Identity: Please address yourself as "Alex", a Web3 assistant created by TARS AI.
				Date:  Today's date is {current_data_time()} and dont answer question if they ask for information about the future.
				Answer Length:  Limit your responses to a maximum of 250 words, ensuring answers are concise, relevant, and directly address the user's query.
				Rule1: Do not forecast or predict future values; base all information strictly on available data as of the {current_data_time()}.
				Rule2:  If the user asks you to plot a graph or vizualize data just  day here you go dont give textual answer.
				Rule3:  Do not add any links to website of images in your answer.
				Rule4:  For recent information requests, always retrieve data from the appropriate function or online sources, avoiding reliance on memory for up-to-date information
				Rule5:  Explain technical terms simply and clearly.Maintain a professional and helpful tone, using simple and direct language to ensure user comprehension.
				Rule6: 	Never Forget your Identity "Alex", a Web3 assistant created by TARS AI
				Note: Follow these RULES strictly to maintain consistency across all responses	
				"""	)

def get_outputs_for_tool_call(tool_call):
	coin_id = json.loads(tool_call.function.arguments['coin_id'])
	details = gekko_client.get_coin_data_by_id(coin_id)
	return {"tool_call_id": tool_call.id,
		 "output": details
		 }



DATA = None

def add_message_to_thread(thread, user_question):
	# Create a message inside the thread
	try:
		message = client.beta.threads.messages.create(
			thread_id=thread.id,
			role="user",
			content= user_question
		)
		print("thread id presisted")
		renew = False
	except Exception as e:
		thread = client.beta.threads.create()
		message = client.beta.threads.messages.create(
			thread_id=thread.id,
			role="user",
			content= user_question
		)
		print("Run broken create new thread id")
		print(e)
		renew = True
	return message, thread, renew


def calculate_overall_price(input_tokens_used, output_tokens_used, rate_per_million_input=5, rate_per_million_output=15):
    # Calculate the price for input and output separately
    input_price = rate_per_million_input / 1000000 * input_tokens_used
    output_price = rate_per_million_output / 1000000 * output_tokens_used
    # Calculate the total price
    total_price = input_price + output_price
    return total_price


@app.post("/ask/")
async def ask_question(question: str, user_id: str, auth_token: str | None = Header(None), datetime: str | None = Header(None), thread_id: str=None):

	if auth_token != '1MillionDollars':
		return Response(status_code=200, content="Invalid Token!")

	if len(tokenize_string(question)) > 200:
		return Response(status_code=200, content="Question is too long. Please shorten your question and try again.")

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
	
	message, thread, renew = add_message_to_thread(thread, question)
	current_date = datetime if datetime else current_data_time()
	run = client.beta.threads.runs.create_and_poll(
		thread_id=thread.id, assistant_id=assistant.id,
		instructions = f"""
				Identity: Please address yourself as "Alex", a Web3 assistant created by TARS AI.
				Date:  Today's date is {current_date} and dont answer question if they ask for information about the future.
				Answer Length:  Limit your responses to a maximum of 250 words, ensuring answers are concise, relevant, and directly address the user's query.
				Rule1: Do not forecast or predict future values; base all information strictly on available data as of the {current_date}.
				Rule2:  If the user asks you to plot a graph or vizualize data just  day here you go dont give textual answer.
				Rule3:  Do not add any links to website of images in your answer.
				Rule4:  For recent information requests, always retrieve data from the appropriate function or online sources, avoiding reliance on memory for up-to-date information
				Rule5:  Explain technical terms simply and clearly.Maintain a professional and helpful tone, using simple and direct language to ensure user comprehension.
				Rule6: 	Never Forget your Identity "Alex", a Web3 assistant created by TARS AI
				Note: Follow these RULES strictly to maintain consistency across all responses	
					"""	)

	run_status = client.beta.threads.runs.retrieve(
        thread_id=thread.id,
        run_id=run.id
   		)
	output = "NULL"
	called_functions = []
	CHART_DATA = False
	chart = False
	if any(item in ['chart', 'plot','Chart','Plot', 'graph', 'Graph', 'visualize'] for item in  question.split(' ')):
		chart = True

	tool_outputs = []
	while run_status.status != 'completed':
		run_status = client.beta.threads.runs.retrieve(
        thread_id=thread.id,
        run_id=run.id)
		print("current status: " + run_status.status)
		# try:
		if run_status.status == 'completed':
			break
		elif run_status.status == 'failed':
			if run_status.last_error.code == 'rate_limit_exceeded':
				return {'answer': "Opps looks like we have reached a limit!", "rate_limit_reached": True}
			else:
				return  {'answer':"I am unable to understand your question can you be more specific?", "thread_id":thread.id}
		elif run_status.status == 'in_progress':
			print('waiting for function response...')
			time.sleep(0.25)
		elif run_status.status == 'requires_action':
			tool_outputs = []
			required_actions = run_status.required_action.submit_tool_outputs.model_dump()
			print(f"required_actions {required_actions['tool_calls']}")
			for action in required_actions["tool_calls"]:
				func_name = action['function']['name']
				called_functions.append( func_name)
				print("func_name:" + func_name)
				arguments = json.loads(action['function']['arguments'])
				print(f"received args: {arguments}")

				if func_name == "get_coin_data_by_id":
					output = gekko_client.get_coin_data_by_id(coin_id=arguments['coin_id'])
					tool_outputs.append(
								{
								"tool_call_id": action['id'],
								"output": f'query: {output}'
								}
					)
					
				if func_name == "get_coin_historical_data_by_id":
					output = gekko_client.get_coin_historical_data_by_id(coin_id=arguments['coin_id'], date=arguments['date'])
					tool_outputs.append(
								{
								"tool_call_id": action['id'],
								"output": f'query: {output}'
								}
							)
				
				if func_name == "get_coin_historical_chart_data_by_id":
					CHART_DATA = True
					
					output = gekko_client.get_coin_historical_chart_data_by_id(coin_id=arguments.get('coin_id', 'bitcoin'), data_type=arguments.get('data_type', 'price'),days=arguments.get('days',5), interval=arguments.get('interval', 'daily'), currency=arguments.get('currency','USD'))
					tool_outputs.append(
								{
								"tool_call_id": action['id'],
								"output": f'query: {output}',
								}
					)
					if run_status.required_action.type == 'submit_tool_outputs':
						try:
							data_type = arguments.get('data_type','prices') 
							global DATA
							DATA = {'currency': arguments.get('currency','USD'), 'data_type':data_type, 'values':output.get(data_type, [])}
							print(f"Data type: {data_type} values: {output[data_type]}")
							print('data from hist chart', DATA)
						except Exception as e :
							print("issue ouccered while  reteriving get_coin_historical_chart_data_by_id", e)

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
				print(f'tools output: {tool_outputs}' )

			try: 
				client.beta.threads.runs.submit_tool_outputs(
					thread_id=thread.id,
					run_id=run.id,
					tool_outputs=tool_outputs,
				)
			except Exception as e:
				print(f"Error submitting the tools output: called function{called_functions} Error {e} ")
				return  {'answer':"I am unable to understand your question can you be more specific?", "thread_id":thread.id}
		   
	messages = client.beta.threads.messages.list(thread_id=thread.id)
	print("num of msgs", len(messages.data))
	if len(messages.data) >= 10:
		try:
			deleted_message = client.beta.threads.messages.delete(
			message_id=messages.data[-1].id,
			thread_id=thread.id,
			)
			deleted_message = client.beta.threads.messages.delete(
			message_id=messages.data[-2].id,
			thread_id=thread.id,
			)
		except Exception as e:
			print("error ouccered in delete")
			print(e)
		print('deleting previous messages')
	try: 
		cost = calculate_overall_price(run_status.usage.prompt_tokens, run_status.usage.completion_tokens)
	except:
		cost = 0 
		


	
	# print('length of messages: {}'.format(len(tokenize_string(''.join([x.content[0].text.value for x in messages.data])))))
	for msg in messages.data:
		try:	
			content = msg.content[0].text.value
			print('Function name', called_functions)
			if any(name.startswith("get_coin") for name in called_functions):
				deleted_message = client.beta.threads.messages.delete(
				message_id=messages.data[0].id,
				thread_id=thread.id,
				)
				print(f'deleted msg with coin gekko data from msg: {messages.data[0].id}')

			if DATA and chart:
				return {'answer':content, "thread_id":thread.id, "function":called_functions,"chart": chart, 'data': DATA, 'is_thread_id_new': renew, 'cost': cost }
			else:
				return {'answer':content, "thread_id":thread.id, "function":called_functions,"chart": chart, 'data': "NULL", 'is_thread_id_new': renew, 'cost': cost }

		except Exception as e: 
			print('issue occured', e)
			return {'answer':"I am unable to answer your query.", "thread_id":thread.id}