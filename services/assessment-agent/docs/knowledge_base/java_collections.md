# Java Collections Framework

## Overview

The Java Collections Framework provides a unified architecture for representing and manipulating collections. It includes interfaces, implementations, and algorithms.

## Core Interfaces

### Collection
The root interface in the collection hierarchy. Represents a group of objects (elements).

### List
An ordered collection (sequence). Allows duplicate elements.

### Set
A collection that contains no duplicate elements.

### Map
An object that maps keys to values. Cannot contain duplicate keys.

## Common Implementations

### ArrayList
- Resizable array implementation
- Fast random access O(1)
- Slow insertion/deletion in middle O(n)

```java
List<String> list = new ArrayList<>();
list.add("Java");
list.add("Python");
list.get(0); // "Java"
```

### LinkedList
- Doubly-linked list implementation
- Fast insertion/deletion O(1)
- Slow random access O(n)

### HashSet
- Hash table implementation of Set
- No duplicates
- O(1) add, remove, contains

```java
Set<Integer> set = new HashSet<>();
set.add(1);
set.add(2);
set.contains(1); // true
```

### HashMap
- Hash table implementation of Map
- O(1) get, put, remove
- No guaranteed order

```java
Map<String, Integer> map = new HashMap<>();
map.put("Alice", 95);
map.get("Alice"); // 95
map.containsKey("Alice"); // true
```

### TreeMap
- Red-Black tree implementation
- O(log n) operations
- Keys sorted in natural order

### PriorityQueue
- Heap-based priority queue
- O(log n) add/poll
- Elements ordered by priority

## Iterating Collections

```java
// For-each loop
for (String item : list) {
    System.out.println(item);
}

// Iterator
Iterator<String> it = list.iterator();
while (it.hasNext()) {
    System.out.println(it.next());
}

// Streams (Java 8+)
list.stream()
    .filter(s -> s.startsWith("J"))
    .forEach(System.out::println);
```

## Collections Utility Methods

```java
Collections.sort(list);
Collections.reverse(list);
Collections.shuffle(list);
Collections.max(list);
Collections.min(list);
Collections.unmodifiableList(list);
```
