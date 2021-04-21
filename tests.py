from decorators import baseinit, call, assign, assignargs, property_store, autocreate

class base1:
    def __init__(self, param):
        print(param)

class base2:
    pass

@baseinit(kwargs={"param": 2})
class outer(base1):
    props = property_store()
    op1 = props.reactive(1)

    @autocreate
    class inner(base2):
        parent = autocreate.parent_reference()
        props = property_store()
        ip1 = props.reactive(2)
        
        @autocreate
        def worm(self):
            print("Worm")
            return "worm"

        @parent.op1.add_callback
        def inner_on_op1(self, source):
            print( ("inner_on_op1", self,source) )
        
        @autocreate
        class inner_inner:
            parent = autocreate.parent_reference()
            props = property_store()
            iip1 = props.reactive(3)
        
            @parent.parent.op1.add_callback
            def inner_inner_on_op1(self, source):
                print( ("inner_inner_on_op1",self,source) )
            
            @props.cached(iip1, parent.ip1, parent.parent.op1)
            def iip2(self):
                print("calculating iip2")
                return ("iip2",self.iip1, self.parent.ip1, self.parent.parent.op1)
    
    @inner.ip1.add_callback
    def outer_on_ip1(self, source):
        print( ("outer_on_ip1", self,source) )

    @inner.inner_inner.parent.parent.inner.inner_inner.parent.parent.op1.add_callback
    def in_and_out(self,source):
        print( ("in_and_out",self,source) )

    @props.cached(op1,inner.ip1,inner.inner_inner.iip1)
    def op2(self):
        print("calculating op2")
        return ("op2",self.op1,self.inner.ip1,self.inner.inner_inner.iip1)

    @autocreate
    def op3(self):
        print("calculating op3")
        return 42

print("creating outer")
o = outer()
print("o.op1 = 4")
o.op1 = 4
print("o.inner.ip1 = 5")
o.inner.ip1 = 5
print("o.inner.inner_inner.iip1 = 6")
o.inner.inner_inner.iip1 = 6
print("o.op3")
o.op3
print("o.inner.worm")
o.inner.worm
