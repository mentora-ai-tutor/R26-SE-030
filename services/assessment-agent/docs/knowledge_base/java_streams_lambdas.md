# Java Streams and Lambda Expressions

## Lambda Expressions

Lambdas provide a concise way to implement functional interfaces.

```java
// Syntax: (parameters) -> expression or (parameters) -> { statements }

// No parameters
Runnable r = () -> System.out.println("Hello");

// Single parameter
Consumer<String> printer = s -> System.out.println(s);

// Multiple parameters
Comparator<String> comp = (a, b) -> a.compareTo(b);

// With body
Function<String, Integer> length = s -> {
    int len = s.length();
    return len;
};
```

## Functional Interfaces

| Interface | Method | Description |
|-----------|--------|-------------|
| Function<T,R> | R apply(T) | Transforms T to R |
| Consumer<T> | void accept(T) | Consumes T |
| Supplier<T> | T get() | Supplies T |
| Predicate<T> | boolean test(T) | Tests T |
| BiFunction<T,U,R> | R apply(T,U) | Two args |
| UnaryOperator<T> | T apply(T) | Identity transform |
| BinaryOperator<T> | T apply(T,T) | Combine two T |

## Stream API

### Creating Streams

```java
// From collection
Stream<String> stream = list.stream();
Stream<String> parallel = list.parallelStream();

// From array
Stream<int[]> arrStream = Arrays.stream(array);

// From values
Stream<String> ofStream = Stream.of("a", "b", "c");

// Generate
Stream<Double> randoms = Stream.generate(Math::random).limit(10);

// Iterate
Stream<Integer> nums = Stream.iterate(0, n -> n + 2).limit(5);
```

### Intermediate Operations (lazy)

```java
list.stream()
    .filter(s -> s.length() > 3)        // Filter elements
    .map(String::toUpperCase)           // Transform elements
    .sorted()                           // Sort
    .distinct()                         // Remove duplicates
    .limit(5)                           // Take first 5
    .skip(2)                            // Skip first 2
    .peek(System.out::println);         // Debug
```

### Terminal Operations

```java
// Collect
List<String> result = list.stream()
    .filter(s -> s.startsWith("J"))
    .collect(Collectors.toList());

// Reduce
int sum = numbers.stream()
    .reduce(0, Integer::sum);

// ForEach
list.stream().forEach(System.out::println);

// Count
long count = list.stream().filter(s -> s.length() > 3).count();

// Find
Optional<String> first = list.stream().findFirst();
Optional<String> any = list.stream().findAny();

// Match
boolean allMatch = list.stream().allMatch(s -> s.length() > 0);
boolean anyMatch = list.stream().anyMatch(s -> s.contains("Java"));
boolean noneMatch = list.stream().noneMatch(s -> s.isEmpty());

// Min/Max
Optional<String> min = list.stream().min(String::compareToIgnoreCase);
Optional<String> max = list.stream().max(String::compareToIgnoreCase);

// Grouping
Map<Integer, List<String>> grouped = list.stream()
    .collect(Collectors.groupingBy(String::length));

// Partitioning
Map<Boolean, List<String>> partitioned = list.stream()
    .collect(Collectors.partitioningBy(s -> s.startsWith("J")));

// Joining
String joined = list.stream()
    .collect(Collectors.joining(", "));
```

### Map-Reduce Pattern

```java
int totalLength = list.stream()
    .map(String::length)
    .reduce(0, Integer::sum);

// or more idiomatically
int totalLength2 = list.stream()
    .mapToInt(String::length)
    .sum();
```
