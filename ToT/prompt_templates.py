generation_prompt_template = \
'''{instructions}

Make a plan then generate the output. If given a Draft Plan, then refine the Draft Plan and then generate the output. Your output should be of the following format:

Plan:
Your plan here.

Output:
Your {output_name} here'''

passage_generation_instuction_template = \
'''I will provide you with four sentences. Your task is to write a coherent passage of four short paragraphs, each paragraph ending with one of my given sentences in the provided order. The four sentences are: {sentences}'''

vote_prompt = \
'''Given an instruction and several choices, decide which choice is most promising. Analyze each choice in detail, then conclude in the LAST LINE WITH THIS EXACT PATTERN "The best choice is {s}", where s is the integer id of the choice.'''