# Java Generics

## Why Generics?

Generics enable type-safe code that works with any type. They eliminate the need for explicit casting and catch type errors at compile time.

## Generic Classes

```java
public class Box<T> {
    private T content;

    public Box(T content) {
        this.content = content;
    }

    public T getContent() {
        return content;
    }

    public void setContent(T content) {
        this.content = content;
    }
}

// Usage
Box<String> stringBox = new Box<>("Hello");
String value = stringBox.getContent(); // No cast needed
```

## Multiple Type Parameters

```java
public class Pair<K, V> {
    private K key;
    private V value;

    public Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    public K getKey() { return key; }
    public V getValue() { return value; }
}

Pair<String, Integer> entry = new Pair<>("age", 25);
```

## Bounded Type Parameters

```java
// Upper bound: T must be Number or subclass
public class MathBox<T extends Number> {
    private T value;

    public double doubleValue() {
        return value.doubleValue();
    }
}

// Multiple bounds
public class SortableBox<T extends Comparable<T> & Serializable> {
    // T must implement both Comparable and Serializable
}
```

## Wildcards

```java
// Upper bounded wildcard: read from collection
public double sum(List<? extends Number> list) {
    return list.stream()
        .mapToDouble(Number::doubleValue)
        .sum();
}

// Lower bounded wildcard: write to collection
public void addNumbers(List<? super Integer> list) {
    list.add(1);
    list.add(2);
}

// Unbounded wildcard: any type
public void printList(List<?> list) {
    for (Object item : list) {
        System.out.println(item);
    }
}
```

## Generic Methods

```java
public static <T extends Comparable<T>> T findMax(List<T> list) {
    T max = list.get(0);
    for (T item : list) {
        if (item.compareTo(max) > 0) {
            max = item;
        }
    }
    return max;
}

// Usage
Integer max = findMax(List.of(3, 1, 4, 1, 5));
String maxStr = findMax(List.of("apple", "banana", "cherry"));
```

## Type Erasure

At runtime, generic type information is erased. `List<String>` and `List<Integer>` are both `List` at runtime.

```java
// This compiles but is unsafe
List<String> strings = new ArrayList<>();
List integers = strings; // Warning, but compiles
// integers.add(42); // ClassCastException at runtime
```

## Best Practices

1. Use bounded types when you need to access methods on type parameters
2. Prefer `extends` for read-only access, `super` for write-only access
3. Use `? extends T` for producer, `? super T` for consumer (PECS principle)
4. Avoid raw types (unparameterized generics)
5. Don't use `instanceof` to check generic types
