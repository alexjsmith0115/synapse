package com.synapsetest;

public class Dog extends Animal {
    public Dog(String name) {
        super(name);
    }

    @Override
    public String speak() {
        return "Woof!";
    }

    public void fetch(String item) {
        speak();
        Formatter.format(item);
    }
}
