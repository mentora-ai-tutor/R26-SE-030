JAVA_TOPICS = [
    "Loops",
    "Arrays",
    "OOP",
    "Recursion",
    "Data Structures",
    "Algorithms",
    "Exception Handling",
    "Collections",
    "Interfaces",
    "Threads",
]

WEIGHTS = {"sandbox": 0.40, "forensic": 0.30, "quiz": 0.30}

MASTERY_PROFILE_SCHEMA_VERSION = "kaa-lmg-v1.0"

TOPIC_CATALOG = {
    "Loops": {
        "topic_id": "CS101-LOOP",
        "prerequisite_topics": ["Variables", "Conditionals"],
        "related_topics": ["Arrays", "Iteration Patterns"],
        "subskills": [
            {
                "subskill": "basic loop syntax",
                "subskill_id": "CS101-LOOP-BASIC",
                "focus": "Review for/while loop structure and counter updates.",
                "misconception": "confuses loop initialization, condition, and update order",
            },
            {
                "subskill": "nested loops",
                "subskill_id": "CS101-LOOP-NESTED",
                "focus": "Use row-column tracing and dry-run tables.",
                "misconception": "does not trace inner loop execution correctly",
            },
            {
                "subskill": "loop boundary conditions",
                "subskill_id": "CS101-LOOP-BOUNDARY",
                "focus": "Practice start/end values and inclusive versus exclusive bounds.",
                "misconception": "uses incorrect loop termination boundaries",
            },
        ],
    },
    "Arrays": {
        "topic_id": "CS101-ARR",
        "prerequisite_topics": ["Loops"],
        "related_topics": ["Collections", "Searching"],
        "subskills": [
            {
                "subskill": "array indexing",
                "subskill_id": "CS101-ARR-INDEX",
                "focus": "Practice zero-based indexing and valid index ranges.",
                "misconception": "confuses array length with the last valid index",
            },
            {
                "subskill": "array traversal",
                "subskill_id": "CS101-ARR-TRAVERSE",
                "focus": "Trace arrays with loop counters and bounds.",
                "misconception": "skips or repeats elements while traversing arrays",
            },
        ],
    },
    "OOP": {
        "topic_id": "CS201-OOP",
        "prerequisite_topics": ["Classes", "Methods"],
        "related_topics": ["Inheritance", "Interfaces"],
        "subskills": [
            {
                "subskill": "class design",
                "subskill_id": "CS201-OOP-CLASS",
                "focus": "Separate fields, constructors, and methods clearly.",
                "misconception": "mixes object state with local method variables",
            },
            {
                "subskill": "inheritance and super calls",
                "subskill_id": "CS201-OOP-INH",
                "focus": "Practice constructor chaining and method overriding.",
                "misconception": "uses inheritance without understanding constructor flow",
            },
        ],
    },
    "OOP - Inheritance": {
        "topic_id": "CS201-INH",
        "prerequisite_topics": ["Classes", "Constructors"],
        "related_topics": ["Polymorphism", "Interfaces"],
        "subskills": [
            {
                "subskill": "constructor chaining",
                "subskill_id": "CS201-INH-SUPER",
                "focus": "Practice super() calls and parent initialization order.",
                "misconception": "does not understand when parent constructors run",
            },
            {
                "subskill": "method overriding",
                "subskill_id": "CS201-INH-OVERRIDE",
                "focus": "Compare overriding with overloading through small examples.",
                "misconception": "confuses overriding with overloading",
            },
        ],
    },
    "Recursion": {
        "topic_id": "CS101-REC",
        "prerequisite_topics": ["Loops", "Functions", "Call Stack"],
        "related_topics": ["Tree Traversal", "Divide and Conquer"],
        "subskills": [
            {
                "subskill": "base case identification",
                "subskill_id": "CS101-REC-BASE",
                "focus": "Practice identifying stopping conditions before writing code.",
                "misconception": "treats the base case as optional or secondary",
            },
            {
                "subskill": "stack frame tracing",
                "subskill_id": "CS101-REC-STACK",
                "focus": "Trace call frames, return values, and recursion depth.",
                "misconception": "cannot explain how recursive calls return",
            },
            {
                "subskill": "recursive return composition",
                "subskill_id": "CS101-REC-RETURN",
                "focus": "Practice combining recursive results correctly.",
                "misconception": "loses return values across recursive calls",
            },
        ],
    },
    "Data Structures": {
        "topic_id": "CS201-DS",
        "prerequisite_topics": ["Arrays", "OOP"],
        "related_topics": ["Algorithms", "Collections"],
        "subskills": [
            {
                "subskill": "data structure selection",
                "subskill_id": "CS201-DS-SELECT",
                "focus": "Compare lists, maps, sets, and trees by operation.",
                "misconception": "chooses structures without considering access patterns",
            },
            {
                "subskill": "operation complexity",
                "subskill_id": "CS201-DS-COMPLEXITY",
                "focus": "Connect common operations to time complexity.",
                "misconception": "does not connect operations to performance cost",
            },
        ],
    },
    "Binary Search Trees": {
        "topic_id": "CS201-BST",
        "prerequisite_topics": ["Recursion", "Trees", "References"],
        "related_topics": ["AVL Trees", "Hash Tables"],
        "subskills": [
            {
                "subskill": "BST insertion and search",
                "subskill_id": "CS201-BST-SEARCH",
                "focus": "Trace comparisons from root to leaf.",
                "misconception": "does not preserve the left-less/right-greater invariant",
            },
            {
                "subskill": "BST deletion cases",
                "subskill_id": "CS201-BST-DELETE",
                "focus": "Practice leaf, one-child, and two-child deletion separately.",
                "misconception": "cannot handle deletion for nodes with two children",
            },
            {
                "subskill": "tree traversal order",
                "subskill_id": "CS201-BST-TRAVERSE",
                "focus": "Trace inorder, preorder, and postorder outputs.",
                "misconception": "confuses traversal order and output sequence",
            },
        ],
    },
    "Algorithms": {
        "topic_id": "CS201-ALG",
        "prerequisite_topics": ["Loops", "Arrays"],
        "related_topics": ["Data Structures", "Complexity Analysis"],
        "subskills": [
            {
                "subskill": "algorithm tracing",
                "subskill_id": "CS201-ALG-TRACE",
                "focus": "Dry-run algorithm state step by step.",
                "misconception": "jumps to final answers without tracing state changes",
            },
            {
                "subskill": "complexity reasoning",
                "subskill_id": "CS201-ALG-COMPLEXITY",
                "focus": "Estimate time complexity from loops and recursive calls.",
                "misconception": "counts statements without understanding growth rate",
            },
        ],
    },
    "Exception Handling": {
        "topic_id": "CS102-EXC",
        "prerequisite_topics": ["Control Flow", "Methods"],
        "related_topics": ["File I/O", "Logging"],
        "subskills": [
            {
                "subskill": "checked versus unchecked exceptions",
                "subskill_id": "CS102-EXC-CHECKED",
                "focus": "Compare compile-time handling requirements.",
                "misconception": "confuses checked and unchecked exception rules",
            },
            {
                "subskill": "try-catch-finally control flow",
                "subskill_id": "CS102-EXC-FLOW",
                "focus": "Trace execution through try, catch, and finally blocks.",
                "misconception": "does not predict which block executes after an exception",
            },
        ],
    },
    "File I/O": {
        "topic_id": "CS102-FILE",
        "prerequisite_topics": ["Exception Handling"],
        "related_topics": ["Streams", "Serialization"],
        "subskills": [
            {
                "subskill": "file read/write flow",
                "subskill_id": "CS102-FILE-RW",
                "focus": "Practice opening, reading/writing, and closing resources.",
                "misconception": "does not manage resources across success and failure paths",
            },
            {
                "subskill": "file exception handling",
                "subskill_id": "CS102-FILE-EXC",
                "focus": "Handle missing files and permission failures explicitly.",
                "misconception": "ignores file operation failure modes",
            },
        ],
    },
}
