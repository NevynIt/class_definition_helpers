"""
CLASS DEFINITION HELPERS

CLASS
    @baseinit(class_to_decorate=None, *, args=(), kwargs={}, mixargs=False)
        updates the __init__ to automatically call super().__init__ at the beginning
        can also be used directly without parameters, and in that case will call the base_class without parameters
        if args or kwargs = None, pass the (kw)arguments passed to __init__ to the base __init__
        if mixargs = True, then limitedly to the arguments included in args and kwargs (if not None), the ones received in the call replace the default given to the decorator

MEMBER FUNCTION DECORATORS
    @call(function_to_call, *, args=(), kwargs={}, append=False, mixargs=False)
        returns a decorator that calls function_to_call before (or after if append==True) the decorated function is executed
        args and kwargs are used in the call to function_to_call unless they are set to None
        in that case, the args or kwargs passed to the decorated function are also passed to function_to_call
        mixargs works the same as in baseinit

    @assign(**kwargs)
        decorates the function so that the kwargs are assigned to self before execution
    
    @assignargs(**kwargs)
        similar to assign, but also passes the kwargs as parameters, and updates the default value with any kwarg that is passed at runtime
        NOTE: the arguments MUST be in the same order as the positional parameters of the function, and positional parameters will take precedence

    @indexable
        decorates a method so that it can be called also as if it the __getitem__ of an array

    @monkey_method
        decorates a method so that a new function can be assigned at runtime and will bind on the object
        as if it was a method defined in the class (i.e. will get self when called)

MEMBER PROPERTY DESCRIPTORS
    property_store:
        add an instance of property_store as a class member and use it to create (and store at runtime) other properties
        use these methods of the descriptor to get descriptors for various types of properties:
            observable(default_value = None, *, readonly = false)
                base class for all the others, automatically creates the instance member and assigns the default_value as soon as it is accessed
                if readonly, will raise an exception if one tries to set value
                includes the following
                    value
                        get/set property
                    check_circular_binding(target)
                        called to see if the properties referenced by this one include target
                        if so, a circular binding is identified and the function raises an exception
                    reactive
                        readonly property to identify reactive properties at runtime

            reactive(default_value = None, *, readonly = false)
                base class for the next ones
                instances includes the following methods
                    add_callback(fnc, key=None)
                        promises to call fnc(source) as soon as the value of the property has changed, if key == None, key will be id(fnc)
                        returns fnc, so it can be used as a decorator
                    del_callback(key)
                        removed the callback fnc from the list
                    alert(reason = None)
                        receives a notification from source, the default behaviour is to pass the alert to the observers as is
                    raise_alert(reason = None)
                        internal implementation to call each of the callbacks
                        if source = none, will pass self to each callback
                the descriptor itself includes
                    add_callback(fnc, key=None)
                        promises to call fnc(source) bound to the actual instance as soon as the value of the property has changed
                        fnc should take a single argument, which will be the reason of the alert
                        the reason is a tuple of object, with the "closest" reasons first, and the very initial reason last
                        NOTE:
                            DO NOT use add_callback on property descriptors from other classes (not even base classes) in this way, as it would break these classes
                            use inherited() to create a reference to the base class property and add callbacks to it
                    del_callback(key)
                        removed the callback fnc from the list
            
            inherited()
                creates a copy of the same property from the base class, so that new observers can be added without breaking the base class
                use this for adding callbacks or cached object that depend on properties of the base class
                inherited is a class method, so it can be used to adding callbacks without defining a specific property store for the subclass
            
            bindable(default_value = None, *, readonly = false)
                special property that can be set to a reference to something else
                if it is not bound or if the something else is reactive, then the property is also reactive
                circular references are immediately checked on binding, and raise an exception
            
            cached(*dependencies, getter=None)
                creates a property whose value is calculated using getter on access (lazy)
                the result of the function is cached, and a callback is added that invalidates the cache as soon as any of the reactive objects in the dependencies raises an alert
                this can be used as a decorator as well
                    import ThisModule as cdh
                    class MyClass:
                        props = cdh.property_store()
                        p1 = props.reactive(1)
                        @props.cached(p1)
                        def p2(self):
                            return p1*2
            
            constant(value)
                creates a property that always returns the same value
                this property derives from reactive even if will never alert, as the value never changes
                constant is a classmethod, so it can be created even without creating an actual property_store
        
        Once the class is instanciated, the property store instance is automatically created as soon as any property is accessed
        it can be used to get instances of the storage object associated to the properties (in order to add_callbacks, invalidate, bind, etc...)
        or to get an autogenerated observable that can be used to bind a boundable property (of any other object) to any member of this instance

    @autocreate
        allows creation of complex composed objects, in which some members are at the same time totally bound to the container but also instances of different classes
        decorates a class declared inside another class
        returns a descriptor that creates an instance of the class on access, and assigns it to the instance, in a member with the same name as the class
        the class gives access to autocreate.parent_reference(), which gives access to the containing class
        decorating a member function will result in a write-once-read-many member variable that is initialised on access with the provided function and cached thereafter

Example usage: see tests.py
"""

import types, inspect, weakref
from collections import namedtuple

__all__ = ("baseinit", "call", "assign", "assignargs", "property_store", "autocreate")

class observable:
    class instance_helper:
        def __init__(self, descriptor):
            self._value = descriptor.default_value
            self.init_done = False #keep for debug for now
        
        def init_instance(self, descriptor, instance):
            if self.init_done: #keep for debug for now
                raise RuntimeError("Instance initialised twice")
            self.init_done = True #keep for debug for now

        @property
        def value(self):
            return self._value
        
        @value.setter
        def value(self, v):
            self._value = v

        def check_circular_binding(self, tgt):
            pass

        @property
        def reactive(self):
            return False

    def __init__(self, default_value = None, *, store = None, readonly = False):
        self.store = store
        self.default_value = default_value
        self.readonly = readonly
    
    def __set_name__(self, owner, name):
        self.name = name
        self.store.slots[name] = self

    def get_slot(self, instance):
        store = getattr(instance, self.store.name)
        return getattr(store, self.name)

    def __get__(self, instance, owner=None):
        if instance == None:
            return observable_reference(self)
        return self.get_slot(instance).value

    def __set__(self, instance, value):
        if self.readonly:
            raise AttributeError(f"Property {self.name} of class {type(instance).__name__} is readonly")
        self.get_slot(instance).value = value

    def copy(self):
        tmp = type(self)(default_value=self.default_value, readonly=self.readonly, store=self.store)
        tmp.name = self.name
        return tmp

class observable_reference(observable):
    def __init__(self, ref):
        vars(self)["_ref"] = ref
    
    def __set_name__(self, owner, name):
        pass

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        return self._ref(instance, owner)
    
    def get_slot(self, instance):
        return self._ref.get_slot(instance)

    def __set__(self, instance, value):
        self._ref.__set__(instance, value)
    
    def __getattr__(self, name):
        return getattr(self._ref, name)
    
    # def __setattr__(self,name,value):
    #     setattr(self._ref,name,value)
    
    def copy(self):
        return self._ref.copy()

class property_store:
    class attribute_reference(observable.instance_helper):
        def __init__(self, instance, name):
            #no need to call the base class
            self.instance = instance
            self.name = name

        def init_instance(self, descriptor, instance):
            raise AttributeError("attribute_reference objects should not be included in property_store slots") #TODO: use a different exception type

        @property
        def value(self):
            return getattr(self.instance, self.name)
        
        @value.setter
        def value(self, v):
            setattr(self.instance, self.name, v)

        def check_circular_binding(self, tgt):
            if tgt is self:
                #TODO: use a different exception type
                raise RuntimeError(f"Circular binding, found in {self.name} of {self.instance}")
            descriptor = getattr(type(self.instance),self.name, None)
            if isinstance(descriptor, observable):
                descriptor.get_slot(self.instance).check_circular_binding(tgt)

        @property
        def reactive(self):
            return False

    class instance_helper:
        def create_slots(self, slots):
            for k, v in slots.items():
                vars(self)[k] = type(v).instance_helper(v)

        def init_slots(self, slots, instance):
            vars(self)["_instance"] = instance
            for k, v in slots.items():
                getattr(self, k).init_instance(v, instance)

        def __getattr__(self, name):
            #try to check if we have real observable first (maybe from another store or a constant)
            descriptor = getattr(type(self._instance),name, None)
            if isinstance(descriptor, observable):
                return descriptor.get_slot(self._instance)
            #otherwise return a reference bound to instance.name
            return property_store.attribute_reference(self._instance, name)

        def __setattr__(self, name, value):
            if isinstance(getattr(self, name), bindable.instance_helper):
                getattr(self, name).binding = value
            else:
                raise AttributeError(f"{name} is not a bindable property for class {type(self._instance).__name__}")

    def __init__(self):
        self.name = None
        self.slots = {}

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        if not self.name in vars(instance):
            store = property_store.instance_helper()
            vars(instance)[self.name] = store
            slots = self.get_slots(owner)
            store.create_slots(slots)
            store.init_slots(slots, instance)
        return vars(instance)[self.name]
    
    def get_slots(self, owner):
        mro = inspect.getmro(owner)
        slots = {}
        for cl in reversed(mro):
            store = vars(cl).get(self.name, None)
            if isinstance(store, property_store):
                slots.update(store.slots)
        return slots

    def __set_name__(self, owner, name):
        if self.name != None:
            raise AttributeError("The same property_store is assigned twice to a class")
        self.name = name
    
    def observable(self, *args, **kwargs):
        return observable(*args, **kwargs, store=self)
    
    def reactive(self, *args, **kwargs):
        return reactive(*args, **kwargs, store=self)
    
    def bindable(self, *args, **kwargs):
        return bindable(*args, **kwargs, store=self)
    
    def cached(self, *args, **kwargs):
        "returns a decorator that creates a cached property that is invalidated when any of the observables passed as arguments is modified"
        return cached(*args, **kwargs, store=self)

    @classmethod
    def constant(self, *args, **kwargs):
        return constant(*args, **kwargs)
    
    @classmethod
    def inherited(self):
        return inherited_reference()
    
    #TODO: maybe useful??
    # def bind(self,target, source):
    #     "ensures that, at runtime, target will be bound to source"
    #     raise NotImplementedError

alert_reason = namedtuple("alert_reason", ("originator","event","args"))

class reactive(observable):
    alert_params = namedtuple("alert_params", ("old_value","new_value")) #this should have a better name

    class instance_helper(observable.instance_helper):
        def __init__(self, descriptor):
            super().__init__(descriptor)
            self.observers = {}
        
        def init_instance(self, descriptor, instance):
            super().init_instance(descriptor, instance)
            for v in descriptor.observers.values():
                self.add_callback(types.MethodType(v, instance))

        @property
        def value(self):
            return self._value
        
        @value.setter
        def value(self, v):
            old_value = self._value
            self._value = v
            self.raise_alert( (alert_reason(self,"set",reactive.alert_params(old_value, v)),) )

        def check_circular_binding(self, tgt):
            pass

        def add_callback(self, fnc, key=None):
            if key == None:
                key = id(fnc)
            if isinstance(fnc, types.MethodType):
                fnc = weakref.WeakMethod(fnc)
            self.observers[key] = fnc
            return key

        def del_callback(self, key):
            del self.observers[key]

        def raise_alert(self, reason):
            for k, v in list(self.observers.items()):
                if isinstance(v, weakref.WeakMethod):
                    fnc = v()
                    if fnc:
                        fnc(reason)
                    else:
                        del self.observers[k] #TODO: not really tested yet!!
                else:
                    fnc(reason)
        
        def alert(self, reason):
            self.raise_alert(reason)

        @property
        def reactive(self):
            return True

    def __init__(self, default_value = None, *, store = None, readonly = False):
        super().__init__(default_value=default_value,store=store, readonly=readonly)
        self.observers = {}

    def __get__(self, instance, owner=None):
        if instance == None:
            return reactive_reference(self)
        return self.get_slot(instance).value

    def add_callback(self, fnc, key=None):
        if key == None:
            key = id(fnc)
        self.observers[key] = fnc
        return fnc

    def del_callback(self, key):
        del self.observers[key]

    def copy(self):
        tmp = type(self)(default_value=self.default_value, readonly=self.readonly, store=self.store)
        tmp.name = self.name
        tmp.observers = dict(self.observers)
        return tmp

class reactive_reference(reactive):
    def __init__(self, ref):
        vars(self)["_ref"] = ref
    
    def __set_name__(self, owner, name):
        pass
    
    def get_slot(self, instance):
        return self._ref.get_slot(instance)

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        return self._ref(instance, owner)
    
    def __set__(self, instance, value):
        self._ref.__set__(instance, value)
    
    def __getattr__(self, name):
        return getattr(self._ref, name)
    
    # def __setattr__(self,name,value):
    #     setattr(self._ref,name,value)

    def add_callback(self, fnc, key=None):
        return self._ref.add_callback(fnc,key)

    def del_callback(self, key):
        self._ref.del_callback(key)
    
    def copy(self):
        return self._ref.copy()

class inherited_reference(reactive):
    def __set_name__(self, owner, name):
        parent = getattr(super(owner,owner), name)
        tmp = parent.copy()
        #if the inherited descriptor was not reactive, this will throw
        for key, fnc in self.observers.items():
            tmp.add_callback(fnc, key)
        #replace the descriptor
        setattr(owner,name,tmp)

class constant(reactive, reactive.instance_helper):
    def __init__(self, value):
        self._value = value
    
    @property
    def readonly(self):
        return True

    def __set_name__(self, owner, name):
        pass

    def get_slot(self, instance):
        return self

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        return self._value

    def __set__(self, instance, value):
        raise AttributeError(f"Cannot set a constant property")
    
    def add_callback(self, fnc, key=None):
        pass

    def del_callback(self, key):
        pass

    def init_instance(self, descriptor, instance):
        raise AttributeError("constant objects should not be included in property_store slots")

    @property
    def value(self):
        return self._value

    def check_circular_binding(self, tgt):
        pass

    @property
    def reactive(self):
        return True
    
    def raise_alert(self, reason):
        raise RuntimeError("Constant property cannot really alert for modification!")
    
    def alert(self, reason):
        pass #ignore alerts

    def copy(self):
        return self

class default():
    def __init__(self, value):
        self._value = value

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        return vars(instance).get(self.name, self._value)

    def __set__(self, instance, value):
        vars(instance)[self.name] = value

class bindable(reactive):
    alert_params = namedtuple("alert_params", ("bound","target"))

    class instance_helper(reactive.instance_helper):
        def __init__(self, descriptor):
            super().__init__(descriptor)
            self.bound = False
            self.default_value = descriptor.default_value

        @property
        def value(self):
            if self.bound:
                return self._value.value
            else:
                return self._value
        
        @value.setter
        def value(self, v):
            if self.bound:
                self._value.value = v #do not alert twice, let the bond do the alert
            else:
                old_value = self._value
                self._value = v
                self.raise_alert( (alert_reason(self,"set",reactive.alert_params(old_value, v)),) )

        @property
        def binding(self):
            if self.bound:
                return self._value
            else:
                return None
        
        def check_circular_binding(self, tgt):
            if tgt is self:
                #TODO: use a different exception type
                raise RuntimeError(f"Circular binding, found in {self}")
            if self.bound:
                self._value.check_circular_binding(tgt)

        @binding.setter
        def binding(self, value):
            old_bound = self.bound
            old_value = self._value

            if value == None:
                if self.bound == True and self._value.reactive:
                    self._value.del_callback(id(self)) #check it is reactive first
                self.bound = False
                self._value = self.default_value
            elif isinstance(value, observable.instance_helper):
                value.check_circular_binding(self)
                if self.bound == True and self._value.reactive:
                    self._value.del_callback(id(self))
                self.bound = True
                self._value = value
                if self._value.reactive:
                    self._value.add_callback(self.bound_alert, id(self))
            else:
                if self.bound == True and self._value.reactive:
                    self._value.del_callback(id(self))
                self.bound = False
                self._value = value
            self.raise_alert( (alert_reason(self,"bind",reactive.alert_params(bindable.alert_params(old_bound,old_value),bindable.alert_params(self.bound, self._value))),) )

        def bound_alert(self, reason):
            self.raise_alert( (alert_reason(self,reason[0].event,reason[0].args),) + reason )
        
        @property
        def reactive(self):
            if self.bound:
                return self._value.reactive
            return True

class cached(reactive):
    alert_params = namedtuple("alert_params", ("old_value",) )
    class instance_helper(reactive.instance_helper):
        def __init__(self, descriptor):
            super().__init__(descriptor)
            self.valid = False
            self.dependencies = []
        
        def init_instance(self, descriptor, instance):
            super().init_instance(descriptor, instance)
            self.getter = types.MethodType(descriptor.getter, instance)
            for dep in descriptor.dependencies:
                slot = dep.get_slot(instance)
                slot.check_circular_binding(self)
                if not slot.reactive:
                    raise RuntimeError(f"Cached object dependencies must be reactive: found in {descriptor.name} of class {type(instance).__name__}")
                slot.add_callback(self.invalidate)
                self.dependencies.append(slot)

        def invalidate(self, reason):
            self.valid = False
            old_value = self._value
            self._value = None
            # for dep in self.dependencies: #this could be more clever and only check the object that raised the alert
            #     if not dep.reactive:
            if reason[0].originator in self.dependencies and not reason[0].originator.reactive:
                raise RuntimeError("Cached object dependencies must stay reactive all the time")
            self.raise_alert( (alert_reason(self, "invalidate", cached.alert_params(old_value)), ) + reason)

        @property
        def value(self):
            if not self.valid:
                self.cache = self.getter()
                self.valid = True
            return self.cache

        def check_circular_binding(self, tgt):
            if tgt is self:
                #TODO: use a different exception type
                raise RuntimeError(f"Circular binding, found in {self}")
            for dep in self.dependencies:
                dep.check_circular_binding(tgt)

    def __init__(self, *dependencies, store = None, getter = None):
        super().__init__(store = store, readonly = True)
        self.dependencies = dependencies
        self.getter = getter

    def __call__(self, getter):
        self.getter = getter
        return self

    def copy(self):
        tmp = type(self)(*(list(self.dependencies)), store=self.store, getter=self.getter)
        tmp.name = self.name
        tmp.observers = dict(self.observers)
        return tmp

def call(function_to_call, *, args=(), kwargs={}, append=False, mixargs=False):
    "decorator that prepends or appends a member function call to the decorated member function, putting args or kwargs to None passes the ones given in the call. always returns the value of the decorated function"
    def decorate(function):
        def decorated_function(self, *inner_args, **inner_kwargs):
            nonlocal args, kwargs, append, mixargs
            if args == None:
                targs = inner_args
            else:
                targs = list(args)
                if mixargs: #this could be done in a thousand ways
                    for i in range(min(len(args),len(inner_args))):
                        targs[i] = inner_args[i]
                
            if kwargs == None:
                kwargs = inner_kwargs
            else:
                tkwargs = dict(kwargs)
                if mixargs: #this could be done in a thousand ways
                    for k in kwargs.keys():
                        if k in inner_kwargs:
                            tkwargs[k] = inner_kwargs[k]

            if not append:
                function_to_call(self, *targs, **tkwargs)
            retval = function(self, *inner_args, **inner_kwargs)
            if append:
                function_to_call(self, *targs, **tkwargs)
            return retval
        return decorated_function
    return decorate

def baseinit(class_to_decorate=None, *, args=(), kwargs={}, mixargs=False):
    if class_to_decorate == None:
        #return a decorator
        def decorate(inner_class_to_decorate):
            return baseinit(inner_class_to_decorate, args=args, kwargs=kwargs)
        return decorate
    else:
        #decorate directly
        if isinstance(class_to_decorate, type):
            old_init = class_to_decorate.__init__
            base_init = super(class_to_decorate,class_to_decorate).__init__
            def new_init(self, *inner_args, **inner_kwargs):
                nonlocal args, kwargs, mixargs, old_init, base_init
                if args == None:
                    targs = inner_args
                else:
                    targs = list(args)
                    if mixargs: #this could be done in a thousand ways
                        for i in range(min(len(args),len(inner_args))):
                            targs[i] = inner_args[i]
                    
                if kwargs == None:
                    kwargs = inner_kwargs
                else:
                    tkwargs = dict(kwargs)
                    if mixargs: #this could be done in a thousand ways
                        for k in kwargs.keys():
                            if k in inner_kwargs:
                                tkwargs[k] = inner_kwargs[k]

                base_init(self, *targs, **tkwargs)
                if old_init != base_init:
                    old_init(self, *inner_args, **inner_kwargs)
            class_to_decorate.__init__ = new_init
        else:
            raise TypeError
        return class_to_decorate

def assign(**kwargs):
    def decorate(fnc):
        def decorated_function(self, *inner_args, **inner_kwargs):
            for k,v in kwargs.items():
                setattr(self,k,v)
            return fnc(self, *inner_args, **inner_kwargs)
        #maybe here one could assign a __name__ to the decorated function
        decorated_function.__name__ = f"({fnc.__name__})"
        return decorated_function
    return decorate

def assignargs(**kwargs):
    def decorate(fnc):
        def decorated_function(self, *inner_args, **inner_kwargs):
            tmp = dict(kwargs)
            tmp.update(inner_kwargs)
            for i,k in zip(range(len(inner_args)),list(tmp.keys())[:len(inner_args)]):
                setattr(self,k,inner_args[i])
                del tmp[k]
            for k in kwargs.keys():
                if k in tmp:
        	        setattr(self,k,tmp[k])
            return fnc(self, *inner_args, **tmp)
        return decorated_function
    return decorate

class indexable_method:
    def __init__(self, fnc, obj):
        self.__func__ = fnc
        self.__self__ = obj

    def __getitem__(self,key):
        return self.__func__(self.__self__, key)
    
    def __call__(self, *args, **kwargs):
        return self.__func__(self.__self__, *args, **kwargs)

class indexable:
    def __init__(self, fnc):
        self.func = fnc

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        return indexable_method(self.func, instance)

class monkey_method:
    def __init__(self, fnc):
        self.func = fnc

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        fnc = vars(instance).get(self.name, self.func)
        return types.MethodType(fnc, instance)
    
    def __set__(self, instance, value):
        vars(instance)[self.name] = value
    
    def __delete__(self, instance):
        del vars(instance)[self.name]

class delayed_callback:
    def __init__(self, fnc, prop_path=(), instance_path=()):
        self.prop_path = prop_path
        self.instance_path = instance_path
        self.fnc = fnc

    def __call__(self, instance, source):
        for key in self.instance_path:
            instance = getattr(instance,key)
        self.fnc(instance, source)

    def attach(self, prop):
        "adds callbacks on descriptors"
        new_path = ()
        for key in self.prop_path:
            prop = getattr(prop,key)
            new_path = (key,) + new_path
            if isinstance(prop, parent_reference):
                # assert prop._parent_class == None
                #not created yet, delay again
                prop._delayed_callbacks.append(delayed_callback(self.fnc,self.prop_path[len(new_path):],self.instance_path))
                return
            elif isinstance(prop, autocreate):
                self.instance_path = (prop.parent_reference_member_name, ) + self.instance_path
                if prop.wrapped:
                    prop = prop.wrapped
                else:
                    prop = prop.factory
        prop.add_callback(self)
    
    def add_callback(self, parent):
        "adds callbacks on instances"
        prop = parent
        for key in self.prop_path[:-1]:
            prop = getattr(prop, key)
        descriptor = getattr(type(prop), self.prop_path[-1])
        slot = descriptor.get_slot(prop)
        slot.add_callback(types.MethodType(self, parent))

class attribute_reference:
    def __init__(self, parent, name):
        self.__parent = parent
        self.__name_in_parent = name
    
    def __set_name__(self, owner, name):
        pass

    @property
    def ownerclass(self):
        return self.__parent.ownerclass

    def get_slot(self, instance):
        parent = self.__parent.__get__(instance, self.__parent.ownerclass)
        descriptor = getattr(type(parent), self.__name_in_parent)
        return descriptor.get_slot(parent)     

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        return getattr(self.__parent.__get__(instance, self.ownerclass), self.__name_in_parent)

    def __set__(self, instance, value):
        setattr(self.__parent.__get__(instance, self.ownerclass), self.__name_in_parent, value) #TODO: Test me!

    def __getattr__(self, name):
        return attribute_reference(self, name)
    
    def __call__(self, *args, **kwargs):
        if self.__name_in_parent == "add_callback" and len(args) == 1 and callable(args[0]) and kwargs == {}:
            #used as a decorator for adding a callback
            prop_path = ()
            ptr = self.__parent
            while isinstance(ptr,attribute_reference):
                prop_path = (ptr.__name_in_parent, ) + prop_path
                ptr = ptr.__parent
            if isinstance(ptr, parent_reference) or isinstance(ptr, autocreate):
                ptr._delayed_callbacks.append(delayed_callback(args[0], prop_path))
            else:
                raise TypeError

            return args[0]
        else:
            raise TypeError("'attribute_reference' object is not callable - unless it's a add_callback decorator ;-)")

class parent_reference_host: #this thing is mind blowing.....
    def __init__(self, decorated = None):
        self.__name = None
        self.__decorated = decorated
    
    def __get__(self, instance, owner=None):
        if self.__decorated == None:
            if instance == None:
                return self
            if self.__name in vars(instance):
                return vars(instance)[self.__name]
            else:
                return None
        else:
            # raise NotImplementedError #TODO: a wrapped object will not be connected the first time it is used
            return self.__decorated.__get__(instance,owner)
    
    def __set_name__(self, owner, name):
        self.__name = name
        if self.__decorated != None:
            self.__decorated.__set_name__(owner,name)

    def __set__(self, instance, value):
        if self.__name in vars(instance):
            old_value = vars(instance)[self.__name]
            for k in dir(type(old_value)):
                v =  getattr(type(old_value), k)
                if isinstance(v, parent_reference):
                    v.disconnect(old_value, instance, self.__name)
        if self.__decorated == None:
            vars(instance)[self.__name] = value
        else:
            self.__decorated.__set__(instance,value)
        if value != None:
            for k in dir(type(value)):
                v =  getattr(type(value), k)
                if isinstance(v, parent_reference):
                    v.connect(value, instance, self.__name)

    def __delete__(self,instance):
        if self.__decorated == None:
            del vars(instance)[self.__name]
        else:
            self.__decorated.__delete__(instance)

class parent_reference:
    def __init__(self):
        self.__name = None
        self.__ownerclass = None
        # self._parent_class = None
        self._delayed_callbacks = []
    
    def __set_name__(self, owner, name):
        if self.__name != None and not owner is self.__ownerclass:
            raise AttributeError("The same parent_reference is assigned to two different classes")
        self.__name = name
        self.__ownerclass = owner

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        return vars(instance)[self.__name] #go direct to __dict__
    
    def __getattr__(self, name):
        return attribute_reference(self, name)
    
    def connect(self, instance, host, name):
        assert self.__name in vars(instance), "Parent_reference is already connected"

        vars(instance)[self.__name] = host
        for cb in self._delayed_callbacks:
            raise NotImplementedError #add the triggers

    def disconnect(self, instance, host, name):
        assert not self.__name in vars(instance), "Parent_reference is already disconnected"
        
        for cb in self._delayed_callbacks:
            raise NotImplementedError #remove the triggers
        del vars(instance)[self.__name]

class autocreate:
    parent_reference = parent_reference

    def __init__(self, factory):
        self.name = None
        self.ownerclass = None
        self._delayed_callbacks = []
        if type(factory) is type:
            class wrapper(factory):
                def __init__(child):
                    #init will be called by __get__
                    pass
            wrapper.__qualname__ = factory.__qualname__+"<>"
            wrapper.__module__ = factory.__module__
            wrapper.__name__ = factory.__name__+"<>"
            self.factory = wrapper
            self.wrapped = factory
        else:
            self.factory = factory
            self.wrapped = None

    def __get__(self, instance, owner=None):
        if instance == None:
            return self
        if not self.name in vars(instance):
            vars(instance)[self.name] = None #canary to identify circular references
            if self.wrapped:
                product = self.factory()
                vars(instance)[self.name] = product

                #assign instance to all parent references directly, so that triggers stored in it will not be created twice
                for k in dir(self.wrapped):
                    v = getattr(self.wrapped, k)
                    if isinstance(v, parent_reference):
                        vars(product)[k] = instance
                
                #call the original __init__ -- not sure this should be done here or after the callbacks
                self.wrapped.__init__(product)
                
                #add the callbacks that have been queued in the autocreate descriptor
                for trg in self._delayed_callbacks:
                    trg.prop_path = (self.name, ) + trg.prop_path
                    trg.add_callback(instance)
            else:
                product = self.factory(instance)
                vars(instance)[self.name] = product                

        return vars(instance)[self.name]

    def __set__(self, instance, value):
        raise AttributeError("Autocreated class members are read-only")
    
    def __set_name__(self, owner, name):
        if self.name != None:
            raise AttributeError("The same autocreate is assigned twice to a class")
        self.name = name
        self.ownerclass = owner
        self.parent_reference_member_name = None
        #add the callbacks that have been queued in the parent_references of the inner object
        if self.wrapped:
            factory = self.wrapped
            for k in dir(factory):
                v = getattr(factory, k)
                if isinstance(v, parent_reference):
                    self.parent_reference_member_name = k
                    # v._parent_class = self #not needed
                    for trg in v._delayed_callbacks:
                        trg.instance_path = (name, ) + trg.instance_path
                        trg.attach(owner)

    def __getattr__(self, name): #TODO: fix member names so that they do not obscure too much the user defined __getattr__
        return attribute_reference(self, name)