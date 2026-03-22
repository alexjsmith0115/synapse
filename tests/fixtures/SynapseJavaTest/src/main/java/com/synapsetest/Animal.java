package com.synapsetest;

public abstract class Animal implements IAnimal {
    private final String name;

    public Animal(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    @Override
    public abstract String speak();

    @Override
    public void move() {
        System.out.println(getName() + " is moving");
    }
}
