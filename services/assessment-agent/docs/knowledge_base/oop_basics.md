# Java Object-Oriented Programming

## Classes and Objects

A class is a blueprint for creating objects. Objects are instances of classes that encapsulate data (fields) and behavior (methods).

### Key Concepts

- **Encapsulation**: Bundling data and methods, restricting direct access to some components
- **Inheritance**: Creating new classes from existing ones
- **Polymorphism**: Objects of different types responding to the same interface
- **Abstraction**: Hiding complex implementation details

## Class Declaration

```java
public class Person {
    private String name;
    private int age;

    public Person(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public void setAge(int age) {
        if (age > 0) {
            this.age = age;
        }
    }
}
```

## Inheritance

Inheritance allows a class to inherit fields and methods from another class using the `extends` keyword.

```java
public class Student extends Person {
    private String university;
    private double gpa;

    public Student(String name, int age, String university, double gpa) {
        super(name, age);
        this.university = university;
        this.gpa = gpa;
    }

    public boolean isHonors() {
        return gpa >= 3.5;
    }
}
```

## Polymorphism

Polymorphism allows objects to be treated as instances of their parent class. Method overriding enables runtime polymorphism.

```java
public class Shape {
    public double area() {
        return 0;
    }
}

public class Circle extends Shape {
    private double radius;

    public Circle(double radius) {
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}
```

## Abstract Classes

Abstract classes cannot be instantiated and may contain abstract methods that must be implemented by subclasses.

```java
public abstract class Animal {
    protected String name;

    public abstract void speak();

    public void eat() {
        System.out.println(name + " is eating.");
    }
}
```

## Interfaces

Interfaces define a contract that classes must implement. Since Java 8, they can have default and static methods.

```java
public interface Drawable {
    void draw();

    default void drawBorder() {
        System.out.println("Drawing border");
    }
}

public class Circle implements Drawable {
    @Override
    public void draw() {
        System.out.println("Drawing circle");
    }
}
```
