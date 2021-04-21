# CLASS DEFINITION HELPERS

`import class_definition_helpers as cdh`

TODO:
- write better documentation
- improve tests and examples at the end of the file
- split the single py file in more manageable pieces

## CLASS DECORATORS

`@baseinit(class_to_decorate=None, *, args=(), kwargs={}, mixargs=False)`
- updates the `__init__` to automatically call `super().__init__` at the beginning
can also be used directly without parameters, and in that case will call the
base_class without parameters
- if args or kwargs = None, pass the (kw)arguments passed to `__init__` to the base `__init__`
if `mixargs = True`, then limitedly to the arguments included in `args` and `kwargs` (if not None), the ones received in the call replace the default given to the decorator

## MEMBER FUNCTION DECORATORS

`@call(function_to_call, *, args=(), kwargs={}, append=False, mixargs=False)`
- returns a decorator that calls `function_to_call` before (or after if `append==True`) the decorated function is executed
- `args` and `kwargs` are used in the call to `function_to_call` unless they are set to None
in that case, the args or kwargs passed to the decorated function are also passed to `function_to_call`
- `mixargs` works the same as in `baseinit`

`@assign(**kwargs)`
- decorates the function so that the `kwargs` are assigned to `self` before execution

`@assignargs(**kwargs)`
- similar to assign, but also passes the `kwargs` as parameters, and updates the default value with any kwarg that is passed at runtime

## MEMBER PROPERTY DESCRIPTORS
`property_store`
- add an instance of property_store as a class member and use it to create (and store at runtime) other properties
- use these methods of the descriptor to get descriptors for various types of properties:
    - `observable(default_value = None, *, readonly = false)`
        - base class for all the others, automatically creates the instance member and assigns the default_value as soon as it is accessed
        - if `readonly`, will raise an exception if one tries to set value
        includes the following
            - `value`
                - get/set property
            - `check_circular_binding(target)`
                - called to see if the properties referenced by this one include target
                - if so, a circular binding is identified and the function raises an exception
            - `reactive`
                - readonly property to identify reactive properties at runtime

    - `reactive(default_value = None, *, readonly = false)`
        - base class for the next ones
        - instances includes the following methods
            - `add_callback(fnc, key=None)`
                - promises to call fnc(source) as soon as the value of the property has changed
            - `del_callback(key)`
                - removed the callback fnc from the list
            `alert(reason = None)`
                - receives a notification from source, the default behaviour is to pass the alert to the observers as is
            `raise_alert(reason = None)`
                - internal implementation to call each of the callbacks
                - if source = none, will pass self to each callback
        - the descriptor itself includes
            - `add_callback(fnc, key=None)`
                - promises to call `fnc(reason)` bound to the actual instance as soon as the value of the property has changed
                - fnc should take a single argument, which will be the reason of the alert
                - the reason is a `tuple` of object, with the "closest" reasons first, and the very initial reason last
                - returns `fnc`, so it can be used as a decorator
                - **WARNING**:
                    - DO NOT use property descriptors from other classes (not even base classes) in this way, as it would break these classes
                    - use `inherited()` to create a reference to the base class property and add callbacks to it
            - `del_callback(key)`
                - removed the callback mapped with `key` from the list
    - `inherited()`
        - creates a copy of the same property from the base class, so that new observers can be added without breaking the base class
        - use this to add callbacks or dependencies for cached object that depend on properties of the base class
        - inherited is a class method, so it can be used to add callbacks without defining a specific property store for the subclass
    
    - `bindable(default_value = None, *, readonly = false)`
        - special property that can be set to a reference to something else
        - if it is not bound or if the something else is reactive, then the property is also reactive
        - circular references are immediately checked on binding, and raise an exception
    
    - `cached(*dependencies, getter=None)`
        - creates a property whose value is calculated using getter on access (lazy)
        - the result of the function is cached, and a callback is added that invalidates the cache as soon as any of the reactive objects in the dependencies raises an alert
        - this can be used as a decorator as well
    
    - `constant(value)`
        - creates a property that always returns the same value
        - this property derives from `reactive` even if will never alert, as the value never changes
        - constant is a `classmethod`, so it can be created even without creating an actual `property_store`
    
    - Once the class is instanciated, the property store instance is automatically created as soon as any property is accessed
    - it can be used to get instances of the storage object associated to the properties (in order to add_callbacks, invalidate, bind, etc...)
    - or to get an autogenerated observable that can be used to bind a boundable property (of any other object) to any member of this instance

`@autocreate`
- allows creation of complex composed objects, in which some members are at the same time totally bound to the container but also instances of different classes
    - decorates a class declared inside another class
    - returns a descriptor that creates an instance of the class on access, and assigns it to the instance, in a member with the same name as the class
    - the class gives access to `autocreate.parent_reference()`, which gives access to the containing class
    - decorating a member function will result in a write-once-read-many member variable that is initialised on access with the provided function and cached thereafter

# Example usage:
see tests.py