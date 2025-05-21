tasks = {
    'end_with_random_sentence': {
        'instructions':
            'I will provide you with four sentences. Your task is to write a coherent passage of four short paragraphs, each paragraph ending with one of my given sentences in the provided order. The four sentences are: {sentences}',
        'evaluation':
            'Given an instruction and several choices, decide which choice is most promising. Analyze each choice in detail, then conclude in the LAST LINE WITH THIS EXACT PATTERN "The best choice is {s}", where s is the integer id of the choice.',
        'n_rounds': 2,
        'n_generation_samples': 5,
        'n_voters': 5
    },
    'start_with_random_sentence': {
        'instructions':
            'I will provide you with four sentences. Your task is to write a coherent passage of four short paragraphs, each paragraph starting with one of my given sentences in the provided order. The four sentences are: {sentences}',
        'evaluation':
            'Given an instruction and several choices, decide which choice is most promising. Analyze each choice in detail, then conclude in the LAST LINE WITH THIS EXACT PATTERN "The best choice is {s}", where s is the integer id of the choice.',
        'n_rounds': 2,
        'n_generation_samples': 5,
        'n_voters': 5
    },
    'code_generation': {
        'instructions':
            'Given a code generation task, write most efficient and fully correct code. The task is: {task}',
        'evaluation':
            'Given an instruction and several choices, decide which choice is most promising. Analyze each choice in detail, then conclude in the LAST LINE WITH THIS EXACT PATTERN "The best choice is {s}", where s is the integer id of the choice.',
        'n_rounds': 3,
        'n_generation_samples': 5,
        'n_voters': 5
    }
}