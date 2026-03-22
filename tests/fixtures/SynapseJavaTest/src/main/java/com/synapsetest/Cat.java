package com.synapsetest;

public class Cat extends Animal {
    private final boolean indoor;

    public Cat(String name, boolean indoor) {
        super(name);
        this.indoor = indoor;
    }

    @Override
    public String speak() {
        return "Meow!";
    }

    public boolean isIndoor() {
        return indoor;
    }
}
